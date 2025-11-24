"""
Landlord routes for application management

Endpoints:
- GET /api/landlord/applications - List applications for landlord's properties
- GET /api/landlord/applications/{id} - Get application details
- GET /api/landlord/properties/{property_id}/applications - Get applications for a property
- POST /api/landlord/applications/{id}/review - Review application (submitted → reviewed)
- POST /api/landlord/applications/{id}/approve - Approve application (reviewed → approved)
- POST /api/landlord/applications/{id}/reject - Reject application (reviewed → rejected)
- POST /api/landlord/applications/{id}/request-info - Request more information (reviewed → needs_info)
- POST /api/landlord/applications/{id}/sign - Sign lease
- POST /api/landlord/applications/{id}/activate - Activate lease
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import math

from app.utils.database import get_db
from app.schemas.application import ApplicationResponse, ApplicationListResponse
from app.services.application_service import ApplicationService
from app.models.application import ApplicationStatus
from app.models.property import Property
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User
from app.core.logger import get_logger

router = APIRouter(prefix="/landlord", tags=["Landlord"])
logger = get_logger(__name__)


def verify_landlord_access(property: Property, current_user: User) -> bool:
    """Verify user has access to property (owner, landlord, or agent)"""
    is_owner = property.owner_id == current_user.id
    is_landlord = current_user.has_role("landlord")
    is_agent = current_user.has_role("agent")
    return is_owner or is_landlord or is_agent


@router.get(
    "/applications",
    response_model=ApplicationListResponse,
    summary="Get landlord's applications",
    response_description="Paginated list of applications for properties owned by the landlord with filters",
    tags=["Applications"]
)
async def get_landlord_applications(
    status: Optional[ApplicationStatus] = Query(None, description="Filter by status (EXACT match)"),
    property_id: Optional[int] = Query(None, description="Filter by property ID"),
    applicant_id: Optional[int] = Query(None, description="Filter by applicant ID"),
    date_from: Optional[datetime] = Query(None, description="Filter by created_at >= date_from (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Filter by created_at <= date_to (ISO 8601)"),
    search: Optional[str] = Query(None, description="Search by application ID, property ID, or applicant ID (numeric)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get filtered and paginated applications for properties owned/managed by the authenticated landlord.
    
    **Authorization:**
    - Landlord/agent role required
    - Returns only applications for properties where property.owner_id = current_user.id
    
    **Filters (all use AND logic):**
    - status: EXACT match on application status
    - property_id: Filter by specific property
    - applicant_id: Filter by specific applicant (landlord-only)
    - date_from: Applications created on or after this date
    - date_to: Applications created on or before this date
    - search: Numeric search across application ID, property ID, and applicant ID
    
    **Pagination:**
    - page: Page number (default 1)
    - limit: Items per page (default 20, max 100)
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = ApplicationService(db)
    items, total = service.get_filtered_applications(
        landlord_id=current_user.id,
        status=status,
        property_id=property_id,
        applicant_id=applicant_id,
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
    summary="Get landlord application by ID",
    response_description="Application details",
    tags=["Applications"]
)
async def get_landlord_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific application by ID.
    
    **Authorization:**
    - Landlord/agent role required
    - Can only view applications for properties they own
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Verify property ownership
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if not verify_landlord_access(property, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions - you don't own this property"
        )
    
    return ApplicationResponse.model_validate(app)


@router.get(
    "/properties/{property_id}/applications",
    response_model=List[ApplicationResponse],
    summary="Get applications for a property",
    response_description="List of all applications for a specific property",
    tags=["Applications"]
)
async def get_property_applications(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all applications for a specific property.
    
    **Authorization:**
    - Landlord/agent role required
    - Can only view applications for properties they own
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    # Verify property ownership
    property = db.query(Property).filter(Property.id == property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if not verify_landlord_access(property, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions - you don't own this property"
        )
    
    service = ApplicationService(db)
    apps = service.get_property_applications(property_id)
    return [ApplicationResponse.model_validate(a) for a in apps]


@router.post(
    "/applications/{application_id}/review",
    response_model=ApplicationResponse,
    summary="Review application",
    response_description="Application status updated to REVIEWED",
    tags=["Applications"]
)
async def review_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Review a rental application (mark as reviewed by landlord).
    
    **Enterprise-grade business rules:**
    - Application must be in SUBMITTED status
    - Property must be owned by the landlord
    - Logs review action with timestamp
    
    **Status transition:**
    - SUBMITTED → REVIEWED
    
    **Workflow:**
    1. Tenant submits application (status: SUBMITTED)
    2. Landlord reviews application (status: REVIEWED) ← This endpoint
    3. Landlord approves/rejects (status: APPROVED/REJECTED)
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Verify property ownership
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if not verify_landlord_access(property, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions - you don't own this property"
        )
    
    updated_app = service.review_application(application_id, current_user.id)
    return ApplicationResponse.model_validate(updated_app)


@router.post(
    "/applications/{application_id}/approve",
    response_model=ApplicationResponse,
    summary="Approve application",
    response_description="Application status updated to APPROVED",
    tags=["Applications"]
)
async def approve_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Approve a rental application.
    
    **Enterprise-grade business rules:**
    - Application must be in REVIEWED status (must be reviewed first)
    - Property must be owned by the landlord
    - System checks: tenant has no active lease, property is available
    
    **Status transition:**
    - REVIEWED → APPROVED
    
    **Prerequisite:**
    - Application must be reviewed first using POST /api/landlord/applications/{id}/review
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Verify property ownership
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if not verify_landlord_access(property, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions - you don't own this property"
        )
    
    updated_app = service.approve_application(application_id, current_user.id)
    return ApplicationResponse.model_validate(updated_app)


@router.post(
    "/applications/{application_id}/reject",
    response_model=ApplicationResponse,
    summary="Reject application",
    response_description="Application status updated to REJECTED",
    tags=["Applications"]
)
async def reject_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reject a rental application.
    
    **Enterprise-grade business rules:**
    - Application must be in REVIEWED status (must be reviewed first)
    - Property must be owned by the landlord
    
    **Status transition:**
    - REVIEWED → REJECTED
    
    **Prerequisite:**
    - Application must be reviewed first using POST /api/landlord/applications/{id}/review
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Verify property ownership
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if not verify_landlord_access(property, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions - you don't own this property"
        )
    
    updated_app = service.reject_application(application_id, current_user.id)
    return ApplicationResponse.model_validate(updated_app)


@router.post(
    "/applications/{application_id}/request-info",
    response_model=ApplicationResponse,
    summary="Request more information",
    response_description="Application status updated to NEEDS_INFO",
    tags=["Applications"]
)
async def request_more_info(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Request more information from applicant.
    
    **Enterprise-grade business rules:**
    - Application must be in REVIEWED status (must be reviewed first)
    - Property must be owned by the landlord
    
    **Status transition:**
    - REVIEWED → NEEDS_INFO
    - Tenant can then resubmit (NEEDS_INFO → SUBMITTED → REVIEWED)
    
    **Prerequisite:**
    - Application must be reviewed first using POST /api/landlord/applications/{id}/review
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Verify property ownership
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if not verify_landlord_access(property, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions - you don't own this property"
        )
    
    updated_app = service.request_more_info(application_id, current_user.id)
    return ApplicationResponse.model_validate(updated_app)


@router.post(
    "/applications/{application_id}/sign",
    response_model=ApplicationResponse,
    summary="Sign lease",
    response_description="Application status updated to SIGNED, other applications auto-withdrawn",
    tags=["Applications"]
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
    - Property must be owned by the landlord
    - Tenant cannot have multiple active leases
    - Automatically withdraws all other pending/approved applications for the tenant
    - Sets lease_signed_at timestamp
    
    **Status transition:**
    - APPROVED → SIGNED
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Verify property ownership
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if not verify_landlord_access(property, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions - you don't own this property"
        )
    
    signed_app = service.sign_lease(application_id, current_user.id)
    return ApplicationResponse.model_validate(signed_app)


@router.post(
    "/applications/{application_id}/activate",
    response_model=ApplicationResponse,
    summary="Activate lease",
    response_description="Application status updated to ACTIVE_LEASE, lease is now live",
    tags=["Applications"]
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
    - Property must be owned by the landlord
    - Tenant cannot have multiple active leases
    - Automatically withdraws all other applications for the tenant
    - Property becomes unavailable
    
    **Status transition:**
    - SIGNED → ACTIVE_LEASE
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Verify property ownership
    property = db.query(Property).filter(Property.id == app.property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if not verify_landlord_access(property, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions - you don't own this property"
        )
    
    activated_app = service.activate_lease(application_id, current_user.id)
    return ApplicationResponse.model_validate(activated_app)

