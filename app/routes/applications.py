"""
Application routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.utils.database import get_db
from app.schemas.application import ApplicationResponse, ApplicationCreate, ApplicationUpdate
from app.services.application_service import ApplicationService
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/applications", tags=["applications"])

@router.post("/", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    application_data: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = ApplicationService(db)
    app = service.create_application(application_data, current_user.id)
    return ApplicationResponse.from_orm(app)

@router.get("/", response_model=List[ApplicationResponse])
async def get_user_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = ApplicationService(db)
    apps = service.get_user_applications(current_user.id)
    return [ApplicationResponse.from_orm(a) for a in apps]

@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.applicant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return ApplicationResponse.from_orm(app)

@router.put("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: int,
    application_data: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.applicant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    updated_app = service.update_application(application_id, application_data)
    return ApplicationResponse.from_orm(updated_app)

@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.applicant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    success = service.delete_application(application_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete application")
