"""
Tenant routes for tenant onboarding and profile management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Body, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import math
from app.utils.database import get_db
from app.schemas.tenant import (
    TenantProfileResponse,
    TenantProfileCreate,
    TenantProfileUpdate,
    TenantOnboardingData,
    TenantOnboardingStatus,
    TenantDashboardResponse
)
from app.schemas.application import ApplicationResponse, ApplicationCreate, ApplicationUpdate, ApplicationListResponse
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
    pending_count = len([a for a in all_apps if a.status in [ApplicationStatus.DRAFT, ApplicationStatus.SUBMITTED, ApplicationStatus.REVIEWED]])
    approved_count = len([a for a in all_apps if a.status == ApplicationStatus.APPROVED])
    
    return TenantDashboardResponse(
        profile=TenantProfileResponse.model_validate(profile) if profile else None,
        active_applications_count=active_count,
        pending_applications_count=pending_count,
        approved_applications_count=approved_count,
        has_tenant_role=current_user.has_role("tenant")
    )


@router.get(
    "/leases",
    response_model=List[ApplicationResponse],
    summary="Get tenant leases",
    response_description="List of tenant's active and signed leases"
)
async def get_tenant_leases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get tenant's leases.
    
    Returns applications with status SIGNED or ACTIVE_LEASE for the authenticated tenant.
    Results are ordered by lease_signed_at (most recent first).
    
    **Authorization:**
    - Tenant role required
    - Returns only leases belonging to the authenticated user
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role required to view leases"
        )
    
    service = ApplicationService(db)
    leases = service.get_tenant_leases(current_user.id)
    
    logger.info(
        "tenant_leases_retrieved",
        user_id=current_user.id,
        lease_count=len(leases)
    )
    
    return [ApplicationResponse.model_validate(lease) for lease in leases]


# ------------------- Tenant Application Routes ------------------- #

@router.post(
    "/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create rental application",
    response_description="Created application in DRAFT status",
    tags=["Applications"]
)
async def create_application(
    application_data: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new rental application.
    
    **Enterprise-grade validation:**
    - Tenant role required
    - Cannot apply if already has active lease
    - Cannot apply twice to same property unless previous is rejected/withdrawn
    - Property must be active and available
    
    Application starts in DRAFT status. Use PATCH to submit it.
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role required. Please complete tenant onboarding and get approved first."
        )
    
    service = ApplicationService(db)
    app = service.create_tenant_application(application_data, current_user.id)
    return ApplicationResponse.model_validate(app)


@router.get(
    "/applications",
    response_model=ApplicationListResponse,
    summary="Get tenant's applications",
    response_description="Paginated list of applications for the authenticated tenant with filters",
    tags=["Applications"]
)
async def get_tenant_applications(
    status: Optional[ApplicationStatus] = Query(None, description="Filter by status (EXACT match)"),
    property_id: Optional[int] = Query(None, description="Filter by property ID"),
    date_from: Optional[datetime] = Query(None, description="Filter by created_at >= date_from (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Filter by created_at <= date_to (ISO 8601)"),
    search: Optional[str] = Query(None, description="Search by application ID or property ID (numeric)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get filtered and paginated applications for the authenticated tenant.
    
    **Authorization:**
    - Tenant role required
    - Returns only applications belonging to the authenticated user
    
    **Filters (all use AND logic):**
    - status: EXACT match on application status
    - property_id: Filter by specific property
    - date_from: Applications created on or after this date
    - date_to: Applications created on or before this date
    - search: Numeric search across application ID and property ID
    
    **Pagination:**
    - page: Page number (default 1)
    - limit: Items per page (default 20, max 100)
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role required"
        )
    
    service = ApplicationService(db)
    items, total = service.get_filtered_applications(
        user_id=current_user.id,
        status=status,
        property_id=property_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        page=page,
        limit=limit
    )
    
    pages = math.ceil(total / limit) if total > 0 else 0
    
    return ApplicationListResponse(
        items=[ApplicationResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        limit=limit,
        pages=pages
    )


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationResponse,
    summary="Get tenant application by ID",
    response_description="Application details",
    tags=["Applications"]
)
async def get_tenant_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific application by ID.
    
    **Authorization:**
    - Tenant role required
    - Can only view own applications
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    if app.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return ApplicationResponse.model_validate(app)


@router.patch(
    "/applications/{application_id}",
    response_model=ApplicationResponse,
    summary="Update tenant application",
    response_description="Updated application",
    tags=["Applications"]
)
async def update_tenant_application(
    application_id: int,
    application_data: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an application.
    
    **Enterprise-grade business rules:**
    - Can only update own applications
    - Cannot edit after SUBMITTED unless status is NEEDS_INFO
    - Status transitions are enforced (draft → submitted → reviewed → approved)
    
    **Status transitions:**
    - DRAFT → SUBMITTED: Tenant submits application
    - NEEDS_INFO → SUBMITTED: Tenant resubmits after providing requested info
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    if app.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Enterprise-grade: Enforce editability rules
    if app.status not in [ApplicationStatus.DRAFT, ApplicationStatus.NEEDS_INFO]:
        if app.status in [ApplicationStatus.SUBMITTED, ApplicationStatus.REVIEWED, ApplicationStatus.APPROVED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot edit application in {app.status.value} status. Only DRAFT and NEEDS_INFO applications can be edited.",
                    "field": "application_status",
                    "current_status": app.status.value
                }
            )
    
    updated_app = service.update_tenant_application(application_id, application_data, current_user.id)
    return ApplicationResponse.model_validate(updated_app)


@router.post(
    "/applications/{application_id}/documents",
    response_model=ApplicationResponse,
    summary="Attach documents to application",
    response_description="Application with attached documents",
    tags=["Applications"]
)
async def attach_documents_to_application(
    application_id: int,
    document_ids: List[str] = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Attach documents to an application.
    
    **Enterprise-grade validation:**
    - Can only attach own documents
    - Can only attach to own applications
    - Documents must belong to the tenant
    - Application must be in DRAFT or NEEDS_INFO status
    
    **Document IDs:**
    - List of document file_id (UUID strings)
    - Documents must be uploaded via /api/documents/upload first
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    if app.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    updated_app = service.attach_documents_to_application(
        application_id=application_id,
        document_ids=document_ids,
        user_id=current_user.id
    )
    return ApplicationResponse.model_validate(updated_app)


@router.post(
    "/applications/{application_id}/withdraw",
    response_model=ApplicationResponse,
    summary="Withdraw application",
    response_description="Application status updated to WITHDRAWN",
    tags=["Applications"]
)
async def withdraw_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Withdraw a rental application.
    
    **Enterprise-grade validation:**
    - Tenant role required
    - Can only withdraw own applications
    - Can withdraw from: DRAFT, SUBMITTED, REVIEWED, NEEDS_INFO
    - Cannot withdraw: APPROVED, SIGNED, ACTIVE_LEASE, REJECTED, WITHDRAWN
    
    **Status transition:**
    - Any withdrawable status → WITHDRAWN
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    if app.applicant_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    withdrawn_app = service.withdraw_application(application_id, current_user.id)
    return ApplicationResponse.model_validate(withdrawn_app)
