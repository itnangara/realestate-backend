"""
Email Verification Service for secure email verification flow

Handles:
- Token generation and storage
- Token validation and verification
- Email sending integration
- Rate limiting and security
- Audit logging
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi import HTTPException, status

from app.models.user import User
from app.models.email_verification_token import EmailVerificationToken
from app.services.notification_service import NotificationService
from app.core.logger import get_logger
from decouple import config

logger = get_logger(__name__)

# Configuration
VERIFICATION_TOKEN_EXPIRE_HOURS = int(config("VERIFICATION_TOKEN_EXPIRE_HOURS", default="24"))
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173")
MAX_VERIFICATION_ATTEMPTS = int(config("MAX_VERIFICATION_ATTEMPTS", default="5"))
MAX_EMAILS_PER_HOUR = int(config("MAX_VERIFICATION_EMAILS_PER_HOUR", default="3"))

# Development/Testing bypass -(⚠️ NEVER set to True in production)
EMAIL_VERIFICATION_BYPASS = config("EMAIL_VERIFICATION_BYPASS", default="false").lower() == "true"


class EmailVerificationService:
    """
    Service for email verification token management and verification.
    
    Features:
    - Secure token generation
    - Token expiration (24 hours default)
    - One-time use tokens
    - Rate limiting
    - Audit logging
    """
    
    def __init__(self, db: Session, notifier: NotificationService):
        self.db = db
        self.notifier = notifier
    
    def generate_token(self, user: User) -> str:
        """
        Generate a secure verification token for a user.
        
        Args:
            user: User to generate token for
            
        Returns:
            Verification token string
        """
        # Generate secure random token
        token = secrets.token_urlsafe(32)
        
        # Calculate expiration (24 hours from now)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_TOKEN_EXPIRE_HOURS)
        
        # Create token record
        db_token = EmailVerificationToken(
            user_id=user.id,
            token=token,
            expires_at=expires_at
        )
        
        self.db.add(db_token)
        self.db.commit()
        self.db.refresh(db_token)
        
        logger.info(
            event="verification_token_generated",
            user_id=user.id,
            token_id=db_token.id,
            expires_at=expires_at.isoformat(),
        )
        
        return token
    
    def verify_token(self, token: str) -> Tuple[bool, Optional[User]]:
        """
        Verify an email verification token.
        
        Args:
            token: Verification token to validate
            
        Returns:
            Tuple of (success: bool, user: Optional[User])
        """
        # Find token that hasn't been used
        db_token = self.db.query(EmailVerificationToken).filter(
            and_(
                EmailVerificationToken.token == token,
                EmailVerificationToken.used == False
            )
        ).first()
        
        if not db_token:
            logger.warning(
                event="verification_token_not_found",
                token=token[:8] + "..." if len(token) > 8 else "***",
            )
            return False, None
        
        # Check if token is expired
        if db_token.is_expired:
            logger.warning(
                event="verification_token_expired",
                token_id=db_token.id,
                user_id=db_token.user_id,
                expires_at=db_token.expires_at.isoformat(),
            )
            return False, None
        
        # Get user
        user = self.db.query(User).filter(User.id == db_token.user_id).first()
        if not user:
            logger.error(
                event="verification_user_not_found",
                token_id=db_token.id,
                user_id=db_token.user_id,
            )
            return False, None
        
        # Check if already verified
        if user.is_verified:
            # Mark token as used even though user is already verified
            db_token.used = True
            self.db.commit()
            logger.info(
                event="verification_already_completed",
                user_id=user.id,
                token_id=db_token.id,
            )
            return True, user
        
        # Mark token as used
        db_token.used = True
        
        # Update user verification status
        user.is_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        
        self.db.commit()
        
        logger.info(
            event="email_verification_successful",
            user_id=user.id,
            token_id=db_token.id,
            email=user.email,
        )
        
        return True, user
    
    def send_verification_email(self, user: User, request_id: Optional[str] = None) -> bool:
        """
        Generate token and send verification email to user.
        
        Args:
            user: User to send verification email to
            request_id: Optional request ID for logging correlation
            
        Returns:
            True if email sent successfully, False otherwise
        """
        # Check if already verified
        if user.is_verified:
            logger.warning(
                event="verification_email_already_verified",
                user_id=user.id,
                request_id=request_id,
            )
            return False
        
        # Check if bypass is enabled (development/testing mode)
        if EMAIL_VERIFICATION_BYPASS:
            user.is_verified = True
            user.email_verified_at = datetime.now(timezone.utc)
            self.db.commit()
            
            logger.warning(
                event="email_verification_bypassed",
                user_id=user.id,
                request_id=request_id,
                email=user.email,
                message="EMAIL_VERIFICATION_BYPASS is enabled - user auto-verified without email",
            )
            return True
        
        # Check rate limiting (max 3 emails per hour)
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_tokens = self.db.query(EmailVerificationToken).filter(
            and_(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.created_at >= one_hour_ago
            )
        ).count()
        
        if recent_tokens >= MAX_EMAILS_PER_HOUR:
            logger.warning(
                event="verification_email_rate_limit_exceeded",
                user_id=user.id,
                request_id=request_id,
                recent_tokens=recent_tokens,
                limit=MAX_EMAILS_PER_HOUR,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many verification emails sent. Please wait before requesting another."
            )
        
        # Generate token
        token = self.generate_token(user)
        
        # Build verification link
        verification_link = f"{FRONTEND_URL}/verify-email?token={token}"
        
        # Send email
        success = self.notifier.send_verification_email(
            to_email=user.email,
            user_name=user.full_name,
            verification_link=verification_link
        )
        
        if success:
            logger.info(
                event="verification_email_sent",
                user_id=user.id,
                request_id=request_id,
                email=user.email,
            )
        else:
            logger.error(
                event="verification_email_send_failed",
                user_id=user.id,
                request_id=request_id,
                email=user.email,
            )
        
        return success
    
    def check_verification_attempts(self, token: str) -> bool:
        """
        Check if verification attempts have exceeded the limit.
        
        Args:
            token: Verification token
            
        Returns:
            True if attempts are within limit, False if exceeded
        """
        db_token = self.db.query(EmailVerificationToken).filter(
            EmailVerificationToken.token == token
        ).first()
        
        if not db_token:
            return True  # Token doesn't exist, let verify_token handle it
        
        # Count failed attempts (expired or invalid tokens for this user)
        failed_attempts = self.db.query(EmailVerificationToken).filter(
            and_(
                EmailVerificationToken.user_id == db_token.user_id,
                EmailVerificationToken.used == True
            )
        ).count()
        
        return failed_attempts < MAX_VERIFICATION_ATTEMPTS

