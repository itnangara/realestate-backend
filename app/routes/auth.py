"""
Authentication routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header, Response, Request, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from app.utils.database import get_db
from app.schemas.user import UserCreate, UserOut, Token, UserLogin, UserConflictResponse
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.email_verification_service import EmailVerificationService
from app.services.notification_service import notification_service
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

@router.post(
    "/register",
    response_model=Union[UserOut, UserConflictResponse],
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "User created successfully", "model": UserOut},
        409: {"description": "User already exists", "model": UserConflictResponse},
        400: {"description": "Validation error or username taken"},
    }
)
async def register_user(
    user_data: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    response: Response = Response()
):
    """
    Register a new user with enterprise-grade idempotency protection.
    
    - Returns 201 Created with user object for new users
    - Returns 409 Conflict with user object for existing users (idempotent)
    - Handles race conditions gracefully
    - Includes user object in 409 response for seamless client integration
    """
    request_id = getattr(request.state, "request_id", "unknown")
    user_service = UserService(db)
    auth_service = AuthService(db)
    
    # Check if user already exists by email (idempotency check)
    existing_user = user_service.get_user_by_email(user_data.email)
    if existing_user:
        # Return 409 Conflict with user object (idempotent behavior)
        # This allows clients to continue seamlessly without extra fetch
        logger.info(
            event="user_registration_duplicate",
            request_id=request_id,
            email=user_data.email,
            username=user_data.username,
            existing_user_id=existing_user.id,
            message="User already exists - returning existing user (idempotent)",
        )
        response.status_code = status.HTTP_409_CONFLICT
        return UserConflictResponse(
            detail="User already exists",
            user=existing_user
        )
    
    # Check username uniqueness (non-idempotent - different usernames are different users)
    existing_username = user_service.get_user_by_username(user_data.username)
    if existing_username:
        logger.warning(
            event="user_registration_username_taken",
            request_id=request_id,
            email=user_data.email,
            username=user_data.username,
            message="Username already taken",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create user with error handling for race conditions
    try:
        logger.info(
            event="user_registration_started",
            request_id=request_id,
            email=user_data.email,
            username=user_data.username,
        )
        user = user_service.create_user(user_data)
        
        # Send verification email after user creation
        try:
            verification_service = EmailVerificationService(db, notification_service)
            verification_service.send_verification_email(user, request_id)
            logger.info(
                event="verification_email_sent_on_registration",
                request_id=request_id,
                user_id=user.id,
                email=user.email,
            )
        except Exception as e:
            # Log error but don't fail registration if email fails
            logger.error(
                event="verification_email_failed_on_registration",
                request_id=request_id,
                user_id=user.id,
                email=user.email,
                error=str(e),
                exc_info=True,
            )
            # Continue with registration even if email fails
        
        # Return 201 Created for new user
        logger.info(
            event="user_registration_completed",
            request_id=request_id,
            user_id=user.id,
            email=user.email,
            username=user.username,
        )
        response.status_code = status.HTTP_201_CREATED
        return user
    except IntegrityError as e:
        # Handle race condition - user was created between check and create
        db.rollback()
        
        # Check if it was an email constraint violation
        error_str = str(e.orig).lower()
        if "email" in error_str or "users_email_key" in error_str or "unique constraint" in error_str:
            # User was created by another request - fetch and return existing user
            existing_user = user_service.get_user_by_email(user_data.email)
            if existing_user:
                logger.info(
                    event="user_registration_race_condition_handled",
                    request_id=request_id,
                    email=user_data.email,
                    existing_user_id=existing_user.id,
                    message="Race condition detected - user created by concurrent request",
                )
                # Return 409 Conflict with user object (idempotent)
                response.status_code = status.HTTP_409_CONFLICT
                return UserConflictResponse(
                    detail="User already exists",
                    user=existing_user
                )
        
        # Check if it was a username constraint violation
        if "username" in error_str or "users_username_key" in error_str:
            logger.warning(
                event="user_registration_username_constraint_violation",
                request_id=request_id,
                email=user_data.email,
                username=user_data.username,
                error_type=type(e).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
        
        # Unknown integrity error
        logger.error(
            event="user_registration_constraint_violation",
            request_id=request_id,
            email=user_data.email,
            username=user_data.username,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User creation failed due to constraint violation"
        )

@router.post("/login", response_model=Token)
async def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    user_agent: Optional[str] = Header(None, alias="User-Agent")
):
    """Login user and return access token with refresh token"""
    auth_service = AuthService(db)
    user_service = UserService(db)
    
    # Get user by email
    user = user_service.get_user_by_email(form_data.username)
    if not user or not auth_service.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Check email verification
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your email for verification link.",
            headers={"X-Verification-Required": "true"}
        )
    
    # Create access token
    access_token = auth_service.create_access_token(data={"sub": user.email})
    
    # Create and save refresh token
    refresh_token_plain, _ = auth_service.create_refresh_token_pair(
        user_id=user.id,
        device_info=user_agent
    )
    
    # Update user login tracking
    user.last_login = datetime.now(timezone.utc)
    user.login_count += 1
    db.commit()
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token_plain,
        "token_type": "bearer"
    }

@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str = Header(..., alias="X-Refresh-Token"),
    db: Session = Depends(get_db),
    user_agent: Optional[str] = Header(None, alias="User-Agent")
):
    """Refresh access token using refresh token (with rotation)"""
    auth_service = AuthService(db)
    user_service = UserService(db)
    
    # Validate refresh token
    token_record = auth_service.validate_refresh_token(refresh_token)
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user
    user = user_service.get_user_by_id(token_record.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create new access token
    access_token = auth_service.create_access_token(data={"sub": user.email})
    
    # Rotate refresh token (revoke old, create new)
    new_refresh_token, _ = auth_service.rotate_refresh_token(
        old_token=refresh_token,
        user_id=user.id,
        device_info=user_agent
    )
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }


@router.post("/logout")
async def logout(
    refresh_token: str = Header(..., alias="X-Refresh-Token"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Logout user by revoking refresh token"""
    auth_service = AuthService(db)
    
    # Revoke the refresh token
    revoked = auth_service.revoke_refresh_token(refresh_token)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refresh token not found"
        )
    
    return {"message": "Successfully logged out"}


@router.post("/logout-all")
async def logout_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Logout user from all devices by revoking all refresh tokens"""
    auth_service = AuthService(db)
    
    revoked_count = auth_service.revoke_all_user_tokens(current_user.id)
    
    return {
        "message": f"Successfully logged out from {revoked_count} device(s)"
    }


@router.get("/me", response_model=UserOut)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current authenticated user"""
    return current_user


# Email Verification Routes

@router.post(
    "/send-verification",
    status_code=status.HTTP_200_OK,
    summary="Send email verification",
    response_description="Verification email sent successfully"
)
async def send_verification_email(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send email verification link to the authenticated user.
    
    - Generates a secure verification token
    - Sends verification email with link
    - Rate limited to 3 emails per hour
    - Returns success message
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Check if already verified
    if current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified"
        )
    
    # Initialize service
    verification_service = EmailVerificationService(db, notification_service)
    
    # Send verification email (handles rate limiting internally)
    try:
        verification_service.send_verification_email(current_user, request_id)
    except HTTPException:
        raise  # Re-raise rate limit exceptions
    except Exception as e:
        logger.error(
            event="verification_email_send_error",
            user_id=current_user.id,
            request_id=request_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email"
        )
    
    return {"message": "Verification email sent successfully"}


@router.get(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    summary="Verify email address",
    response_description="Email successfully verified"
)
async def verify_email(
    token: str = Query(..., description="Email verification token"),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Verify email address using verification token.
    
    - Validates token (not expired, not used)
    - Updates user.is_verified = True
    - Updates user.email_verified_at = now()
    - Marks token as used
    - Returns success message
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Initialize service
    verification_service = EmailVerificationService(db, notification_service)
    
    # Verify token
    success, user = verification_service.verify_token(token)
    
    if not success or not user:
        logger.warning(
            event="verification_token_invalid",
            request_id=request_id,
            token=token[:8] + "..." if len(token) > 8 else "***",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    
    logger.info(
        event="email_verification_completed",
        user_id=user.id,
        request_id=request_id,
        email=user.email,
    )
    
    return {"message": "Email successfully verified"}


@router.post(
    "/resend-verification",
    status_code=status.HTTP_200_OK,
    summary="Resend verification email",
    response_description="Verification email resent successfully"
)
async def resend_verification_email(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Resend email verification link to the authenticated user.
    
    - Checks if email is already verified
    - Generates new verification token
    - Sends verification email with new link
    - Rate limited to 3 emails per hour
    - Returns success message
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Check if already verified
    if current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified"
        )
    
    # Initialize service
    verification_service = EmailVerificationService(db, notification_service)
    
    # Send verification email (handles rate limiting internally)
    try:
        verification_service.send_verification_email(current_user, request_id)
    except HTTPException:
        raise  # Re-raise rate limit exceptions
    except Exception as e:
        logger.error(
            event="verification_email_resend_error",
            user_id=current_user.id,
            request_id=request_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend verification email"
        )
    
    logger.info(
        event="verification_email_resent",
        user_id=current_user.id,
        request_id=request_id,
    )
    
    return {"message": "Verification email resent successfully"}
