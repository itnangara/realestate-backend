"""
Tenant routes for tenant onboarding and profile management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List
from app.utils.database import get_db
from app.schemas.tenant import (
    TenantProfileResponse,
    TenantProfileCreate,
    TenantProfileUpdate,
    TenantOnboardingData,
    TenantOnboardingStatus,
    TenantDashboardResponse
)
from app.services.tenant_service import TenantService
from app.services.tenant_onboarding_service import TenantOnboardingService
from app.services.application_service import ApplicationService
from app.models.application import ApplicationStatus
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User
from app.core.logger import get_logger

router = APIRouter(prefix="/tenant", tags=["Tenant"])
logger = get_logger(__name__)


@router.post(
    "/onboarding",
    response_model=TenantProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit tenant onboarding data",
    response_description="Created or updated tenant profile"
)
async def submit_onboarding(
    onboarding_data: TenantOnboardingData,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit tenant onboarding data.
    
    This endpoint:
    - Creates or updates tenant profile with onboarding information
    - Collects personal info, employment, income, rental history, preferences
    - Associates uploaded documents with the profile
    
    Note: Documents should be uploaded separately via /api/documents/upload
    """
    service = TenantOnboardingService(db)
    profile = service.submit_onboarding_data(current_user.id, onboarding_data)
    return TenantProfileResponse.model_validate(profile)


@router.get(
    "/onboarding/status",
    response_model=TenantOnboardingStatus,
    summary="Get tenant onboarding status",
    response_description="Current onboarding status and progress"
)
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current tenant onboarding status.
    
    Returns:
    - Whether onboarding is complete
    - Whether user has tenant role
    - Whether tenant profile exists
    - List of completed and pending steps
    - Tenant profile if exists
    """
    service = TenantOnboardingService(db)
    status_data = service.get_onboarding_status(current_user.id)
    return status_data


@router.get(
    "/onboarding/required-documents",
    response_model=List[dict],
    summary="Get required documents for tenant onboarding",
    response_description="List of required documents with descriptions"
)
async def get_required_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of required documents for tenant onboarding.
    
    Returns document types, names, descriptions, and whether they're required.
    """
    service = TenantOnboardingService(db)
    documents = service.get_required_documents()
    return documents


@router.post(
    "/profile",
    response_model=TenantProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create tenant profile",
    response_description="Created tenant profile"
)
async def create_tenant_profile(
    profile_data: TenantProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new tenant profile.
    
    **Note:** User must have tenant role to create profile.
    If profile already exists, use PUT /api/tenant/profile instead.
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role required. Please complete tenant onboarding and get approved first."
        )
    
    service = TenantService(db)
    profile = service.create_tenant_profile(current_user.id, profile_data)
    return TenantProfileResponse.model_validate(profile)


@router.get(
    "/profile",
    response_model=TenantProfileResponse,
    summary="Get tenant profile",
    response_description="Tenant profile information"
)
async def get_tenant_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's tenant profile.
    
    Returns 404 if profile doesn't exist.
    """
    service = TenantService(db)
    profile = service.get_tenant_profile(current_user.id)
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant profile not found"
        )
    
    return TenantProfileResponse.model_validate(profile)


@router.put(
    "/profile",
    response_model=TenantProfileResponse,
    summary="Update tenant profile",
    response_description="Updated tenant profile"
)
async def update_tenant_profile(
    profile_data: TenantProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update existing tenant profile.
    
    Only provided fields will be updated.
    """
    service = TenantService(db)
    profile = service.update_tenant_profile(current_user.id, profile_data)
    return TenantProfileResponse.model_validate(profile)


@router.get(
    "/dashboard",
    response_model=TenantDashboardResponse,
    summary="Get tenant dashboard",
    response_description="Tenant dashboard summary with profile and application counts"
)
async def get_tenant_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get tenant dashboard data.
    
    Returns:
    - Tenant profile
    - Application counts (active, pending, approved)
    - Whether user has tenant role
    """
    tenant_service = TenantService(db)
    application_service = ApplicationService(db)
    
    profile = tenant_service.get_tenant_profile(current_user.id)
    
    # Get application counts
    all_apps = application_service.get_user_applications(current_user.id)
    active_count = len([a for a in all_apps if a.is_active])
    pending_count = len([a for a in all_apps if a.status == ApplicationStatus.PENDING])
    approved_count = len([a for a in all_apps if a.status == ApplicationStatus.APPROVED])
    
    return TenantDashboardResponse(
        profile=TenantProfileResponse.model_validate(profile) if profile else None,
        active_applications_count=active_count,
        pending_applications_count=pending_count,
        approved_applications_count=approved_count,
        has_tenant_role=current_user.has_role("tenant")
    )

