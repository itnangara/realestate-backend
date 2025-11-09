"""
Role management routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from app.utils.database import get_db
from app.models.role import Role
from app.schemas.role import RoleListResponse
from app.schemas.role_request import (
    RoleRequestCreate,
    RoleRequestResponse,
    RoleRequestListResponse
)
from app.services.role_request_service import RoleRequestService
from app.models.role_request import RoleRequestStatus
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User
from app.core.logger import get_logger

router = APIRouter(tags=["Roles"])
logger = get_logger(__name__)


def get_role_request_service(db: Session = Depends(get_db)) -> RoleRequestService:
    """Dependency to get role request service instance"""
    return RoleRequestService(db)


@router.get(
    "/",
    response_model=List[RoleListResponse],
    summary="List all available system roles",
    response_description="List of all roles in the system (admin-only)."
)
async def list_roles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all available system roles.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    Returns a list of all roles in the system with their details.
    """
    # Restrict to admin users only
    if not current_user.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Admin access required"
        )

    roles = db.query(Role).all()
    return roles


@router.post(
    "/request",
    response_model=RoleRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a role request",
    response_description="Created role request with pending status"
)
async def create_role_request(
    request_data: RoleRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    Submit a request for elevated roles (seller, agent, landlord, investor, tenant).
    
    This endpoint:
    - Validates requested roles
    - Attaches documents if provided
    - Creates a role request with PENDING status
    - Checks KYC requirements based on feature flags
    - Logs the action in audit trail
    
    The request will be processed asynchronously (Phase 5) and may require KYC verification
    depending on the requested roles and feature flag configuration.
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = RoleRequestService(db)
    role_request = await service.create_role_request(
        user_id=current_user.id,
        requested_roles=request_data.requested_roles,
        document_ids=request_data.document_ids,
        notes=request_data.notes,
        request_id=request_id
    )
    
    return RoleRequestResponse.model_validate(role_request)


@router.get(
    "/requests/me",
    response_model=RoleRequestListResponse,
    summary="Get my role requests",
    response_description="List of all role requests for the authenticated user"
)
async def get_my_role_requests(
    status: Optional[RoleRequestStatus] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all role requests for the authenticated user.
    
    Optional query parameter:
    - status: Filter by status (pending, in_review, approved, rejected)
    """
    service = RoleRequestService(db)
    requests = service.get_user_role_requests(
        user_id=current_user.id,
        status_filter=status
    )
    
    return RoleRequestListResponse(
        requests=[RoleRequestResponse.model_validate(req) for req in requests],
        total=len(requests)
    )
