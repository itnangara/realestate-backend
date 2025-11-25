"""
Lease routes for rental lease management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.utils.date_utils import parse_date_query_param

from app.utils.database import get_db
from app.schemas.lease import (
    LeaseCreate, LeaseUpdate, LeaseResponse, LeaseListResponse,
    LeaseSendRequest, LeaseSignRequest
)
from app.services.lease_service import LeaseService
from app.models.lease import LeaseStatus
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User
from app.core.logger import get_logger

router = APIRouter(prefix="/leases", tags=["Leases"])
logger = get_logger(__name__)


@router.post(
    "",
    response_model=LeaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create lease draft",
    response_description="Created lease draft in DRAFT status"
)
async def create_lease(
    lease_data: LeaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a lease draft from an approved application.
    
    **Enterprise-grade business rules:**
    - Application must be in APPROVED status
    - Only landlord/agent can create
    - Property must be owned by the landlord
    - Cannot create duplicate lease for same application
    
    **Status:** Lease starts in DRAFT status
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = LeaseService(db)
    lease = service.create_lease(lease_data, current_user.id)
    
    # Load signatures
    db.refresh(lease)
    return LeaseResponse.model_validate(lease)


@router.get(
    "/{lease_id}",
    response_model=LeaseResponse,
    summary="Get lease by ID",
    response_description="Lease details with signatures"
)
async def get_lease(
    lease_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get lease details by ID.
    
    **Authorization:**
    - Tenant can view their own leases
    - Landlord can view leases for their properties
    """
    service = LeaseService(db)
    lease = service.get_lease_by_id(lease_id)
    
    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found"
        )
    
    # Verify access
    is_tenant = current_user.has_role("tenant") and lease.tenant_id == current_user.id
    is_landlord = (current_user.has_role("landlord") or current_user.has_role("agent")) and lease.landlord_id == current_user.id
    
    if not (is_tenant or is_landlord):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to view this lease"
        )
    
    # 🔒 ENTERPRISE-GRADE ACCESS CONTROL: Tenants cannot view DRAFT leases
    # Tenants may ONLY view leases that have been SENT to them (or later statuses)
    if is_tenant and lease.status == LeaseStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lease not available yet. The landlord has not sent it to you."
        )
    
    return LeaseResponse.model_validate(lease)


@router.get(
    "/application/{application_id}",
    response_model=LeaseResponse,
    summary="Get lease by application ID",
    response_description="Lease details for an application"
)
async def get_lease_by_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get lease by application ID.
    
    **Authorization:**
    - Tenant can view leases for their applications
    - Landlord can view leases for their properties
    """
    service = LeaseService(db)
    lease = service.get_lease_by_application_id(application_id)
    
    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found for this application"
        )
    
    # Verify access
    is_tenant = current_user.has_role("tenant") and lease.tenant_id == current_user.id
    is_landlord = (current_user.has_role("landlord") or current_user.has_role("agent")) and lease.landlord_id == current_user.id
    
    if not (is_tenant or is_landlord):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to view this lease"
        )
    
    # ENTERPRISE-GRADE ACCESS CONTROL: Tenants cannot view DRAFT leases
    if is_tenant and lease.status == LeaseStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lease not available yet. The landlord has not sent it to you."
        )
    
    return LeaseResponse.model_validate(lease)


@router.post(
    "/{lease_id}/send",
    response_model=LeaseResponse,
    summary="Send lease to tenant",
    response_description="Lease status updated to SENT"
)
async def send_lease(
    lease_id: int,
    send_data: Optional[LeaseSendRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send lease to tenant for signing.
    
    **Enterprise-grade business rules:**
    - Lease must be in DRAFT status
    - Only landlord/agent can send
    - Property must be owned by the landlord
    
    **Status transition:** DRAFT → SENT
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = LeaseService(db)
    lease = await service.send_lease(lease_id, current_user.id, send_data.message if send_data else None)
    
    return LeaseResponse.model_validate(lease)


@router.post(
    "/{lease_id}/sign",
    response_model=LeaseResponse,
    summary="Sign lease (tenant)",
    response_description="Lease signed by tenant, status updated to SIGNED"
)
async def sign_lease(
    lease_id: int,
    sign_data: LeaseSignRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Tenant signs the lease.
    
    **Enterprise-grade business rules:**
    - Lease must be in SENT or DRAFT status
    - Only tenant can sign their own lease
    - Idempotent: cannot sign twice
    
    **Status transition:** SENT/DRAFT → SIGNED
    **Application status:** SIGNED (when lease is signed)
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role required"
        )
    
    # Get IP and user agent for audit
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    service = LeaseService(db)
    lease = await service.sign_lease(lease_id, current_user.id, sign_data, ip_address, user_agent)
    
    return LeaseResponse.model_validate(lease)


@router.post(
    "/{lease_id}/counter-sign",
    response_model=LeaseResponse,
    summary="Counter-sign lease (landlord)",
    response_description="Lease counter-signed by landlord, status updated to COUNTER_SIGNED"
)
async def counter_sign_lease(
    lease_id: int,
    sign_data: LeaseSignRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Landlord counter-signs the lease after tenant has signed.
    
    **Enterprise-grade business rules:**
    - Lease must be in SIGNED status (tenant must sign first)
    - Only landlord/agent can counter-sign
    - Property must be owned by the landlord
    
    **Status transition:** SIGNED → COUNTER_SIGNED
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    # Get IP and user agent for audit
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    service = LeaseService(db)
    lease = await service.counter_sign_lease(lease_id, current_user.id, sign_data, ip_address, user_agent)
    
    return LeaseResponse.model_validate(lease)


@router.post(
    "/{lease_id}/activate",
    response_model=LeaseResponse,
    summary="Activate lease",
    response_description="Lease activated, status updated to ACTIVE"
)
async def activate_lease(
    lease_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Activate lease (move to active status).
    
    **Enterprise-grade business rules:**
    - Lease must be COUNTER_SIGNED (both parties signed)
    - Tenant and landlord must have signed
    - Current date must be >= start_date
    - Only landlord/agent can activate
    - Property becomes unavailable
    - Other applications for same tenant/property are withdrawn
    
    **Status transition:** COUNTER_SIGNED → ACTIVE
    **Application status:** ACTIVE_LEASE (if application_id exists)
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = LeaseService(db)
    lease = await service.activate_lease(lease_id, current_user.id)
    
    return LeaseResponse.model_validate(lease)


@router.post(
    "/{lease_id}/terminate",
    response_model=LeaseResponse,
    summary="Terminate lease",
    response_description="Lease terminated, status updated to TERMINATED"
)
async def terminate_lease(
    lease_id: int,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Terminate lease (move to terminated status).
    
    **Enterprise-grade business rules:**
    - Lease must be ACTIVE
    - Can be called by landlord or tenant (with proper authorization)
    - Property becomes available again
    - Application status updated to CLOSED (if application_id exists)
    
    **Status transition:** ACTIVE → TERMINATED
    **Application status:** CLOSED (if application_id exists)
    """
    service = LeaseService(db)
    lease = await service.terminate_lease(lease_id, current_user.id, reason)
    
    return LeaseResponse.model_validate(lease)


@router.get(
    "/landlord/leases",
    response_model=List[LeaseResponse],
    summary="Get landlord's leases",
    response_description="List of all leases for the authenticated landlord"
)
async def get_landlord_leases(
    status: Optional[LeaseStatus] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all leases for the authenticated landlord.
    
    **Authorization:**
    - Landlord/agent role required
    - Returns only leases where landlord_id = current_user.id
    """
    if not (current_user.has_role("landlord") or current_user.has_role("agent")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Landlord or agent role required"
        )
    
    service = LeaseService(db)
    leases = service.get_landlord_leases(current_user.id, status)
    
    return [LeaseResponse.model_validate(lease) for lease in leases]


@router.get(
    "/tenant/leases",
    response_model=List[LeaseResponse],
    summary="Get tenant's leases",
    response_description="List of all leases for the authenticated tenant with optional filtering"
)
async def get_tenant_leases(
    status: Optional[LeaseStatus] = Query(None, description="Filter by lease status"),
    property_id: Optional[int] = Query(None, description="Filter by property ID"),
    date_from: Optional[datetime] = Query(None, description="Filter leases starting from date (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Filter leases ending before date (ISO 8601)"),
    search: Optional[str] = Query(None, description="Search by property title or address"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all leases for the authenticated tenant with optional filtering.
    
    **Authorization:**
    - Tenant role required
    - Returns only leases where tenant_id = current_user.id
    - DRAFT leases are always excluded (tenants cannot see drafts)
    
    **Filtering:**
    - status: Filter by lease status (SENT, SIGNED, COUNTER_SIGNED, ACTIVE, TERMINATED, CANCELLED)
    - property_id: Filter by specific property
    - date_from: Filter leases with start_date >= date_from (ISO 8601 format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - date_to: Filter leases with end_date <= date_to (ISO 8601 format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - search: Search by property title or address (case-insensitive)
    
    **Date Format:**
    - FastAPI automatically parses ISO 8601 dates from query parameters
    - Supports both date-only (YYYY-MM-DD) and datetime (YYYY-MM-DDTHH:MM:SS) formats
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant role required"
        )
    
    service = LeaseService(db)
    leases = service.get_tenant_leases(
        tenant_id=current_user.id,
        status=status,
        property_id=property_id,
        date_from=date_from,
        date_to=date_to,
        search=search
    )
    
    return [LeaseResponse.model_validate(lease) for lease in leases]


@router.get(
    "/properties/{property_id}/leases",
    response_model=List[LeaseResponse],
    summary="Get leases for a property",
    response_description="List of all leases for a specific property"
)
async def get_property_leases(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all leases for a specific property.
    
    **Authorization:**
    - Landlord/agent can view leases for their properties
    - Tenant can view leases for properties they're renting
    """
    from app.models.property import Property
    
    # Verify property exists
    property = db.query(Property).filter(Property.id == property_id).first()
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    # Verify access
    is_landlord = (current_user.has_role("landlord") or current_user.has_role("agent")) and property.owner_id == current_user.id
    is_tenant = current_user.has_role("tenant")
    
    if not (is_landlord or is_tenant):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to view leases for this property"
        )
    
    # If tenant, only show their own leases
    service = LeaseService(db)
    if is_tenant:
        leases = [l for l in service.get_property_leases(property_id) if l.tenant_id == current_user.id]
    else:
        leases = service.get_property_leases(property_id)
    
    return [LeaseResponse.model_validate(lease) for lease in leases]


@router.post(
    "/auto-activate",
    summary="Auto-activate leases (scheduled job)",
    response_description="Number of leases activated",
    tags=["Leases", "Admin"]
)
async def auto_activate_leases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Automatic lease activation endpoint for scheduled jobs.
    
    **Enterprise-grade automation:**
    - Finds all leases with status = COUNTER_SIGNED
    - Activates leases where start_date <= today
    - Returns count of activated leases
    
    **Authorization:** Admin only (for scheduled job access)
    
    **Usage:** Call this endpoint daily via cron job or scheduled task
    """
    if not current_user.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    
    service = LeaseService(db)
    activated_count = await service.auto_activate_leases_on_start_date()
    
    return {
        "activated_count": activated_count,
        "message": f"Activated {activated_count} lease(s)"
    }


@router.get(
    "/{lease_id}/pdf",
    summary="Download lease PDF",
    response_description="Lease document as PDF file",
    responses={
        200: {
            "description": "PDF file",
            "content": {"application/pdf": {}}
        }
    }
)
async def download_lease_pdf(
    lease_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Download lease as PDF document.
    
    **Enterprise-grade business rules:**
    - Tenant can download their own leases
    - Landlord can download leases for their properties
    - Only available for signed/active leases (SIGNED, COUNTER_SIGNED, ACTIVE, TERMINATED)
    
    **Authorization:**
    - Tenant can download their own leases
    - Landlord can download leases for their properties
    """
    from fastapi.responses import Response
    from io import BytesIO
    
    service = LeaseService(db)
    lease = service.get_lease_by_id(lease_id)
    
    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found"
        )
    
    # Verify access
    is_tenant = current_user.has_role("tenant") and lease.tenant_id == current_user.id
    is_landlord = (current_user.has_role("landlord") or current_user.has_role("agent")) and lease.landlord_id == current_user.id
    
    if not (is_tenant or is_landlord):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to download this lease"
        )
    
    # Check if lease is in a downloadable state
    if lease.status not in [LeaseStatus.SIGNED, LeaseStatus.COUNTER_SIGNED, LeaseStatus.ACTIVE, LeaseStatus.TERMINATED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot download lease in {lease.status.value} status. Lease must be signed or active."
        )
    
    # TODO: Implement actual PDF generation
    # For now, return a placeholder PDF or generate using a library like reportlab, weasyprint, etc.
    # This is a placeholder implementation - replace with actual PDF generation
    try:
        # Placeholder: Generate a simple PDF with lease information
        # In production, use a proper PDF library (reportlab, weasyprint, pdfkit, etc.)
        pdf_content = f"""
        LEASE AGREEMENT
        ===============
        
        Lease ID: {lease.id}
        Property ID: {lease.property_id}
        Tenant ID: {lease.tenant_id}
        Landlord ID: {lease.landlord_id}
        
        Monthly Rent: ${lease.rent}
        Security Deposit: ${lease.deposit or 'N/A'}
        
        Start Date: {lease.start_date or 'N/A'}
        End Date: {lease.end_date or 'N/A'}
        
        Status: {lease.status.value}
        
        Terms:
        {lease.terms or 'No terms specified'}
        
        This is a placeholder PDF. Implement proper PDF generation in production.
        """.encode('utf-8')
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=lease-{lease.id}.pdf"
            }
        )
    except Exception as e:
        logger.error(f"Error generating PDF for lease {lease_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate PDF"
        )

