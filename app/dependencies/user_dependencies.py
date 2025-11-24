"""
User dependencies for FastAPI routes
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.utils.database import get_db
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.models.user import User
from app.core.logger import get_logger

logger = get_logger(__name__)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user_email(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Get current user email from token"""
    auth_service = AuthService(db)
    return auth_service.verify_token(token)

def get_current_user(
    db: Session = Depends(get_db), 
    email: str = Depends(get_current_user_email)
) -> User:
    """
    Get current authenticated user.
    
    Enterprise-grade: Returns 401 (not 404) if user doesn't exist.
    This is a security issue - token references non-existent user.
    """
    user_service = UserService(db)
    user = user_service.get_user_by_email(email)
    
    if not user:
        # Enterprise-grade: Log security event for auditing
        logger.warning(
            "invalid_token_user_not_found",
            email=email,
            message="Token references non-existent user - possible deleted account or invalid token"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user
