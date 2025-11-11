"""
Admin routes for moderation and management

Endpoints:
- GET /api/admin/role-requests - List role requests with filters
- POST /api/admin/role-requests/{id}/approve - Approve role request
- POST /api/admin/role-requests/{id}/reject - Reject role request
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.utils.database import get_db
from app.schemas.role_request import RoleRequestResponse, RoleRequestListResponse
from app.services.role_request_service import RoleRequestService
from app.services.role_granting_service import RoleGrantingService
from app.models.role_request import RoleRequest, RoleRequestStatus
from app.dependencies.authorization_dependencies import get_admin_user
from app.models.user import User
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


def get_role_request_service(db: Session = Depends(get_db)) -> RoleRequestService:
    """Dependency to get role request service instance"""
    return RoleRequestService(db)


def get_role_granting_service(db: Session = Depends(get_db)) -> RoleGrantingService:
    """Dependency to get role granting service instance"""
    return RoleGrantingService(db)


@router.get(
    "/role-requests",
    response_model=RoleRequestListResponse,
    summary="List role requests (admin only)",
    response_description="List of role requests with optional filters"
)
async def list_role_requests(
    status_filter: Optional[RoleRequestStatus] = Query(None, description="Filter by status"),
    role: Optional[str] = Query(None, description="Filter by requested role"),
    date_from: Optional[datetime] = Query(None, description="Filter by date from"),
    date_to: Optional[datetime] = Query(None, description="Filter by date to"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    List all role requests with optional filters.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    Query parameters:
    - status: Filter by status (pending, in_review, approved, rejected)
    - role: Filter by requested role name
    - date_from: Filter requests from this date
    - date_to: Filter requests until this date
    - limit: Maximum number of results (1-100, default 50)
    - offset: Number of results to skip (for pagination)
    """
    query = db.query(RoleRequest)
    
    # Apply filters
    if status_filter:
        query = query.filter(RoleRequest.status == status_filter)
    
    if role:
        # Filter by role in requested_roles array (PostgreSQL ARRAY contains)
        query = query.filter(RoleRequest.requested_roles.contains([role]))
    
    if date_from:
        query = query.filter(RoleRequest.requested_at >= date_from)
    
    if date_to:
        query = query.filter(RoleRequest.requested_at <= date_to)
    
    # Get total count before pagination
    total = query.count()
    
    # Apply pagination
    requests = query.order_by(RoleRequest.requested_at.desc()).offset(offset).limit(limit).all()
    
    # Defensive: Ensure requests is always a list (never None)
    # Enterprise-grade: Consistent type safety across all endpoints
    requests_list = requests if requests is not None else []
    
    return RoleRequestListResponse(
        requests=[RoleRequestResponse.model_validate(req) for req in requests_list],
        total=total
    )


@router.get(
    "/role-requests/{role_request_id}",
    response_model=RoleRequestResponse,
    summary="Get role request details (admin only)",
    response_description="Detailed information about a specific role request"
)
async def get_role_request(
    role_request_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific role request.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    Returns:
    - Role request details
    - Attached documents
    - KYC status (if applicable)
    - Review history
    """
    service = RoleRequestService(db)
    role_request = service.get_role_request(role_request_id)
    
    if not role_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role request not found"
        )
    
    return RoleRequestResponse.model_validate(role_request)


@router.post(
    "/role-requests/{role_request_id}/approve",
    response_model=RoleRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve role request (admin only)",
    response_description="Approved role request with roles granted"
)
async def approve_role_request(
    role_request_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    Approve a role request and grant the requested roles to the user.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    This endpoint:
    - Approves the role request
    - Grants all requested roles to the user
    - Sends approval notification email
    - Logs the action in audit trail
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = RoleGrantingService(db)
    role_request = service.approve_role_request(
        role_request_id=role_request_id,
        approved_by=admin_user.id,
        request_id=request_id
    )
    
    return RoleRequestResponse.model_validate(role_request)


@router.post(
    "/role-requests/{role_request_id}/reject",
    response_model=RoleRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject role request (admin only)",
    response_description="Rejected role request"
)
async def reject_role_request(
    role_request_id: int,
    reason: Optional[str] = None,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    Reject a role request.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    This endpoint:
    - Rejects the role request
    - Sends rejection notification email with optional reason
    - Logs the action in audit trail
    
    Request body (optional):
    - reason: Optional rejection reason to include in notification
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = RoleGrantingService(db)
    role_request = service.reject_role_request(
        role_request_id=role_request_id,
        rejected_by=admin_user.id,
        reason=reason,
        request_id=request_id
    )
    
    return RoleRequestResponse.model_validate(role_request)

