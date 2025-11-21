"""
Application routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.utils.database import get_db
from app.schemas.application import ApplicationResponse, ApplicationCreate, ApplicationUpdate
from app.services.application_service import ApplicationService
from app.models.application import ApplicationStatus
from app.models.property import Property
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Applications"])

@router.post("/", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    application_data: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = ApplicationService(db)
    app = service.create_application(application_data, current_user.id)
    return ApplicationResponse.model_validate(app)

@router.get("/", response_model=List[ApplicationResponse])
async def get_user_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = ApplicationService(db)
    apps = service.get_user_applications(current_user.id)
    return [ApplicationResponse.model_validate(a) for a in apps]

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
    return ApplicationResponse.model_validate(app)

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
    return ApplicationResponse.model_validate(updated_app)

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


# ------------------- Landlord/Agent Review Endpoints ------------------- #

@router.get(
    "/property/{property_id}",
    response_model=List[ApplicationResponse],
    summary="Get applications for a property (Landlord/Agent only)",
    response_description="List of all applications for a specific property"
)
async def get_property_applications(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all applications for a property.
    
    **Landlord/Agent only** - User must be the owner of the property or have agent role.
    """
    # Check if property exists
    property = db.query(Property).filter(Property.id == property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    # Check authorization: must be property owner or agent
    is_owner = property.owner_id == current_user.id
    is_agent = current_user.has_role("agent")
    is_landlord = current_user.has_role("landlord")
    
    if not (is_owner or is_agent or is_landlord):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only property owners, landlords, or agents can view applications"
        )
    
    service = ApplicationService(db)
    apps = service.get_property_applications(property_id)
    return [ApplicationResponse.model_validate(a) for a in apps]


@router.post(
    "/{application_id}/accept",
    response_model=ApplicationResponse,
    summary="Accept an application (Landlord/Agent only)",
    response_description="Accepted application"
)
async def accept_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accept a rental application.
    
    **Landlord/Agent only** - User must be the owner of the property.
    """
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Check authorization: must be property owner or agent
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    is_owner = property.owner_id == current_user.id
    is_agent = current_user.has_role("agent")
    is_landlord = current_user.has_role("landlord")
    
    if not (is_owner or is_agent or is_landlord):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only property owners, landlords, or agents can accept applications"
        )
    
    updated_app = service.update_application_status(
        application_id=application_id,
        new_status=ApplicationStatus.APPROVED
    )
    
    if not updated_app:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update application"
        )
    
    return ApplicationResponse.model_validate(updated_app)


@router.post(
    "/{application_id}/reject",
    response_model=ApplicationResponse,
    summary="Reject an application (Landlord/Agent only)",
    response_description="Rejected application"
)
async def reject_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reject a rental application.
    
    **Landlord/Agent only** - User must be the owner of the property.
    """
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Check authorization: must be property owner or agent
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    is_owner = property.owner_id == current_user.id
    is_agent = current_user.has_role("agent")
    is_landlord = current_user.has_role("landlord")
    
    if not (is_owner or is_agent or is_landlord):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only property owners, landlords, or agents can reject applications"
        )
    
    updated_app = service.update_application_status(
        application_id=application_id,
        new_status=ApplicationStatus.REJECTED
    )
    
    if not updated_app:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update application"
        )
    
    return ApplicationResponse.model_validate(updated_app)


@router.post(
    "/{application_id}/request-info",
    response_model=ApplicationResponse,
    summary="Request more information (Landlord/Agent only)",
    response_description="Application status updated to under_review"
)
async def request_more_info(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Request more information from applicant.
    
    **Landlord/Agent only** - User must be the owner of the property.
    Sets application status to UNDER_REVIEW.
    """
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Check authorization: must be property owner or agent
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    is_owner = property.owner_id == current_user.id
    is_agent = current_user.has_role("agent")
    is_landlord = current_user.has_role("landlord")
    
    if not (is_owner or is_agent or is_landlord):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only property owners, landlords, or agents can request more information"
        )
    
    updated_app = service.update_application_status(
        application_id=application_id,
        new_status=ApplicationStatus.UNDER_REVIEW
    )
    
    if not updated_app:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update application"
        )
    
    return ApplicationResponse.model_validate(updated_app)


# ------------------- Lease Management Endpoints ------------------- #

@router.post(
    "/{application_id}/sign",
    response_model=ApplicationResponse,
    summary="Sign lease (Landlord/Agent/Tenant)",
    response_description="Application status updated to SIGNED, other applications auto-withdrawn"
)
async def sign_lease(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Sign a lease (move application to SIGNED status).
    
    **Enterprise-grade business rules:**
    - Application must be APPROVED
    - Tenant cannot have multiple active leases
    - Automatically withdraws all other pending/approved applications for the tenant
    - Sets lease_signed_at timestamp
    
    **Authorization:**
    - Property owner/landlord/agent: Can sign on behalf of tenant
    - Tenant: Can sign their own application
    """
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Check authorization
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    is_owner = property.owner_id == current_user.id
    is_agent = current_user.has_role("agent")
    is_landlord = current_user.has_role("landlord")
    is_tenant = app.applicant_id == current_user.id and current_user.has_role("tenant")
    
    if not (is_owner or is_agent or is_landlord or is_tenant):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only property owners, landlords, agents, or the applicant tenant can sign leases"
        )
    
    try:
        signed_app = service.sign_lease(
            application_id=application_id,
            signed_by_user_id=current_user.id
        )
        return ApplicationResponse.model_validate(signed_app)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "lease_signing_failed",
            application_id=application_id,
            user_id=current_user.id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sign lease: {str(e)}"
        )


@router.post(
    "/{application_id}/activate",
    response_model=ApplicationResponse,
    summary="Activate lease (Landlord/Agent/Tenant)",
    response_description="Application status updated to ACTIVE_LEASE, lease is now live"
)
async def activate_lease(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Activate a lease (move application from SIGNED to ACTIVE_LEASE status).
    
    This represents move-in confirmation - the lease is now live and active.
    
    **Enterprise-grade business rules:**
    - Application must be SIGNED
    - Tenant cannot have multiple active leases
    - Automatically withdraws all other pending/approved applications for the tenant
    
    **Authorization:**
    - Property owner/landlord/agent: Can activate on behalf of tenant
    - Tenant: Can activate their own lease
    """
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Check authorization
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    is_owner = property.owner_id == current_user.id
    is_agent = current_user.has_role("agent")
    is_landlord = current_user.has_role("landlord")
    is_tenant = app.applicant_id == current_user.id and current_user.has_role("tenant")
    
    if not (is_owner or is_agent or is_landlord or is_tenant):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only property owners, landlords, agents, or the applicant tenant can activate leases"
        )
    
    try:
        activated_app = service.activate_lease(
            application_id=application_id,
            activated_by_user_id=current_user.id
        )
        return ApplicationResponse.model_validate(activated_app)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "lease_activation_failed",
            application_id=application_id,
            user_id=current_user.id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate lease: {str(e)}"
        )
