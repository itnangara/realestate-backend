"""
Application routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.schemas.application import ApplicationResponse, ApplicationCreate, ApplicationUpdate
from app.services.application_service import ApplicationService
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.routes.auth import oauth2_scheme

router = APIRouter()

def get_current_user_email(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Get current user email from token"""
    auth_service = AuthService(db)
    return auth_service.verify_token(token)

@router.post("/", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    application_data: ApplicationCreate,
    current_user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Create a new property application"""
    application_service = ApplicationService(db)
    user_service = UserService(db)
    
    # Get current user
    current_user = user_service.get_user_by_email(current_user_email)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Create application
    application = application_service.create_application(application_data, current_user.id)
    return application

@router.get("/", response_model=List[ApplicationResponse])
async def get_user_applications(
    current_user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Get current user's applications"""
    application_service = ApplicationService(db)
    user_service = UserService(db)
    
    # Get current user
    current_user = user_service.get_user_by_email(current_user_email)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    applications = application_service.get_user_applications(current_user.id)
    return applications

@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: int,
    current_user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Get a specific application"""
    application_service = ApplicationService(db)
    user_service = UserService(db)
    
    # Get current user
    current_user = user_service.get_user_by_email(current_user_email)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    application = application_service.get_application_by_id(application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Check if user owns the application
    if application.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return application

@router.put("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: int,
    application_data: ApplicationUpdate,
    current_user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Update an application"""
    application_service = ApplicationService(db)
    user_service = UserService(db)
    
    # Get current user
    current_user = user_service.get_user_by_email(current_user_email)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Check if application exists and user owns it
    application = application_service.get_application_by_id(application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    if application.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Update application
    updated_application = application_service.update_application(application_id, application_data)
    return updated_application
