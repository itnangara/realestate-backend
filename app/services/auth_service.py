"""
Authentication service for JWT and password handling
"""

import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from jose import JWTError, jwt
from passlib.context import CryptContext
from decouple import config
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken, REFRESH_TOKEN_EXPIRE_DAYS

# Configuration
SECRET_KEY = config("SECRET_KEY", default="your-secret-key-change-in-production")
ALGORITHM = config("ALGORITHM", default="HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(config("ACCESS_TOKEN_EXPIRE_MINUTES", default="30"))

# Password hashing - use argon2 only (clean, modern setup)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

class AuthService:
    """Authentication service class"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        now = datetime.now(timezone.utc)
        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def verify_token(self, token: str) -> str:
        """Verify JWT token and return user email"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email: str = payload.get("sub")
            if email is None:
                raise JWTError("Invalid token: missing 'sub' claim")
            return email
        except jwt.ExpiredSignatureError:
            from fastapi import HTTPException, status
            from app.core.logger import get_logger
            logger = get_logger(__name__)
            logger.warning(
                "token_expired",
                message="JWT token has expired"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired. Please refresh your token or login again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except JWTError as e:
            # Log the actual error for debugging (but don't expose to client)
            from fastapi import HTTPException, status
            from app.core.logger import get_logger
            logger = get_logger(__name__)
            logger.warning(
                "jwt_validation_failed",
                error_type=type(e).__name__,
                error_message=str(e),
                message="JWT token validation failed"
            )
            # Re-raise as HTTPException for FastAPI to handle properly
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials. Please login again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    def create_refresh_token(self) -> Tuple[str, str]:
        """Generate a secure refresh token and return (token, hashed_token)"""
        token = secrets.token_urlsafe(64)
        hashed = hashlib.sha256(token.encode()).hexdigest()
        return token, hashed
    
    def hash_refresh_token(self, token: str) -> str:
        """Hash a refresh token for storage"""
        return hashlib.sha256(token.encode()).hexdigest()
    
    def validate_refresh_token(self, token: str) -> Optional[RefreshToken]:
        """Validate refresh token and return RefreshToken if valid"""
        hashed_token = self.hash_refresh_token(token)
        
        refresh_token = self.db.query(RefreshToken).filter(
            RefreshToken.token == hashed_token
        ).first()
        
        if not refresh_token:
            return None
        
        if refresh_token.revoked or refresh_token.is_expired:
            return None
        
        return refresh_token
    
    def revoke_refresh_token(self, token: str, replaced_by: Optional[str] = None) -> bool:
        """Revoke a refresh token"""
        hashed_token = self.hash_refresh_token(token)
        refresh_token = self.db.query(RefreshToken).filter(
            RefreshToken.token == hashed_token
        ).first()
        
        if not refresh_token:
            return False
        
        refresh_token.revoked = True
        if replaced_by:
            refresh_token.replaced_by = replaced_by
        refresh_token.last_used_at = datetime.now(timezone.utc)
        
        self.db.commit()
        return True
    
    def revoke_all_user_tokens(self, user_id: int) -> int:
        """Revoke all active refresh tokens for a user"""
        revoked_count = self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False
        ).update({"revoked": True})
        
        self.db.commit()
        return revoked_count
    
    def create_refresh_token_pair(
        self, 
        user_id: int, 
        device_info: Optional[str] = None
    ) -> Tuple[str, RefreshToken]:
        """Create and save refresh token, return (plain_token, db_token)"""
        plain_token, hashed_token = self.create_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        refresh_token = RefreshToken(
            user_id=user_id,
            token=hashed_token,
            expires_at=expires_at,
            device_info=device_info
        )
        
        self.db.add(refresh_token)
        self.db.commit()
        self.db.refresh(refresh_token)
        
        return plain_token, refresh_token
    
    def rotate_refresh_token(
        self, 
        old_token: str, 
        user_id: int, 
        device_info: Optional[str] = None
    ) -> Tuple[str, RefreshToken]:
        """Rotate refresh token: revoke old, create new"""
        # Revoke old token
        old_hashed = self.hash_refresh_token(old_token)
        old_refresh_token = self.db.query(RefreshToken).filter(
            RefreshToken.token == old_hashed,
            RefreshToken.user_id == user_id
        ).first()
        
        # Create new token
        plain_token, hashed_token = self.create_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        new_refresh_token = RefreshToken(
            user_id=user_id,
            token=hashed_token,
            expires_at=expires_at,
            device_info=device_info
        )
        
        # Mark old token as replaced
        if old_refresh_token:
            old_refresh_token.revoked = True
            old_refresh_token.replaced_by = hashed_token
            old_refresh_token.last_used_at = datetime.now(timezone.utc)
        
        self.db.add(new_refresh_token)
        self.db.commit()
        self.db.refresh(new_refresh_token)
        
        return plain_token, new_refresh_token
