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
    """Get current authenticated user"""
    user_service = UserService(db)
    user = user_service.get_user_by_email(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="User not found"
        )
    return user
