"""
User routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.schemas.user import UserResponse, UserUpdate
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.routes.auth import oauth2_scheme

router = APIRouter()

def get_current_user_email(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Get current user email from token"""
    auth_service = AuthService(db)
    return auth_service.verify_token(token)

@router.get("/me", response_model=UserResponse)
async def get_current_user(
    current_user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Get current user profile"""
    user_service = UserService(db)
    user = user_service.get_user_by_email(current_user_email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user

@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_data: UserUpdate,
    current_user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Update current user profile"""
    user_service = UserService(db)
    user = user_service.get_user_by_email(current_user_email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    updated_user = user_service.update_user(user.id, user_data)
    return updated_user

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_current_user(
    current_user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Deactivate current user account"""
    user_service = UserService(db)
    user = user_service.get_user_by_email(current_user_email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user_service.deactivate_user(user.id)
