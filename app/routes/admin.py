"""
Admin routes for moderation and management

Endpoints:
- GET /api/admin/role-requests - List role requests with filters
- GET /api/admin/role-requests/{id} - Get role request details with documents
- POST /api/admin/role-requests/{id}/approve - Approve role request
- POST /api/admin/role-requests/{id}/reject - Reject role request
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.utils.database import get_db
from app.schemas.admin import (
    AdminRoleRequestResponse, 
    AdminRoleRequestListResponse,
    DocumentAttachmentResponse,
    RoleRequestRejectRequest
)
from app.services.role_request_service import RoleRequestService
from app.services.role_granting_service import RoleGrantingService
from app.services.document_service import DocumentService
from app.models.role_request import RoleRequest, RoleRequestStatus
from app.dependencies.authorization_dependencies import get_admin_user
from app.models.user import User
from app.core.logger import get_logger
from app.schemas.application import ApplicationResponse
from app.services.application_service import ApplicationService

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
    response_model=AdminRoleRequestListResponse,
    summary="List role requests (admin only)",
    response_description="List of role requests with optional filters and document attachments"
)
async def list_role_requests(
    status: Optional[RoleRequestStatus] = Query(None, description="Filter by status (pending, in_review, approved, rejected) - EXACT MATCH"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    role: Optional[str] = Query(None, description="Filter by requested role"),
    date_from: Optional[datetime] = Query(None, description="Filter by date from (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Filter by date to (ISO 8601)"),
    search: Optional[str] = Query(None, description="Search by request ID or user ID"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    List all role requests with optional filters and document attachments.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    Query parameters:
    - status: Filter by status (pending, in_review, approved, rejected) - EXACT MATCH
    - user_id: Filter by specific user ID
    - role: Filter by requested role name (seller, agent, landlord, tenant, investor)
    - date_from: Filter requests from this date (ISO 8601 format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - date_to: Filter requests until this date (ISO 8601 format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    - search: Search by request ID (integer) or user ID (integer)
    - limit: Maximum number of results (1-100, default 50)
    - offset: Number of results to skip (for pagination)
    """
    role_request_service = RoleRequestService(db)
    document_service = DocumentService(db)
    
    # Get role requests with filters (including search)
    requests = role_request_service.get_role_requests_with_documents(
        status_filter=status,
        user_id_filter=user_id,
        role_filter=role,
        date_from=date_from,
        date_to=date_to,
        search_query=search,
        limit=limit,
        offset=offset
    )
    
    # Get total count for pagination (must match the same filters)
    total = role_request_service.count_role_requests(
        status_filter=status,
        user_id_filter=user_id,
        role_filter=role,
        date_from=date_from,
        date_to=date_to,
        search_query=search
    )
    
    # Build response with document attachments
    requests_with_docs = []
    for req in requests:
        attachments = []
        if req.attachments:
            # Get documents by file_ids (UUIDs)
            file_id_strings = [str(att) for att in req.attachments]
            documents = document_service.get_documents_by_file_ids_admin(file_id_strings)
            
            # Get documents with presigned URLs
            docs_with_urls = document_service.get_documents_with_urls(documents, expires_in=3600)
            
            # Convert to DocumentAttachmentResponse
            attachments = [
                DocumentAttachmentResponse(**doc_data) 
                for doc_data in docs_with_urls
            ]
        
        requests_with_docs.append(AdminRoleRequestResponse(
            id=req.id,
            user_id=req.user_id,
            requested_roles=req.requested_roles,
            status=req.status,
            requested_at=req.requested_at,
            reviewed_by=req.reviewed_by,
            reviewed_at=req.reviewed_at,
            notes=req.notes,
            attachments=attachments,
            trust_score=req.trust_score
        ))
    
    logger.info(
        "admin_role_requests_listed",
        admin_user_id=admin_user.id,
        total=total,
        returned=len(requests_with_docs)
    )
    
    return AdminRoleRequestListResponse(
        requests=requests_with_docs,
        total=total
    )


@router.get(
    "/role-requests/{role_request_id}",
    response_model=AdminRoleRequestResponse,
    summary="Get role request details (admin only)",
    response_description="Detailed information about a specific role request with document attachments"
)
async def get_role_request(
    role_request_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific role request with document attachments.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    Returns:
    - Role request details
    - Attached documents with presigned URLs
    - Review history
    """
    role_request_service = RoleRequestService(db)
    document_service = DocumentService(db)
    
    role_request = role_request_service.get_role_request_with_documents(role_request_id)
    
    if not role_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role request not found"
        )
    
    # Get document attachments with URLs
    attachments = []
    if role_request.attachments:
        file_id_strings = [str(att) for att in role_request.attachments]
        documents = document_service.get_documents_by_file_ids_admin(file_id_strings)
        docs_with_urls = document_service.get_documents_with_urls(documents, expires_in=3600)
        attachments = [
            DocumentAttachmentResponse(**doc_data) 
            for doc_data in docs_with_urls
        ]
    
    logger.info(
        "admin_role_request_retrieved",
        admin_user_id=admin_user.id,
        role_request_id=role_request_id,
        attachments_count=len(attachments)
    )
    
    return AdminRoleRequestResponse(
        id=role_request.id,
        user_id=role_request.user_id,
        requested_roles=role_request.requested_roles,
        status=role_request.status,
        requested_at=role_request.requested_at,
        reviewed_by=role_request.reviewed_by,
        reviewed_at=role_request.reviewed_at,
        notes=role_request.notes,
        attachments=attachments,
        trust_score=role_request.trust_score
    )


@router.post(
    "/role-requests/{role_request_id}/approve",
    response_model=AdminRoleRequestResponse,
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
    
    role_granting_service = RoleGrantingService(db)
    role_request = role_granting_service.approve_role_request(
        role_request_id=role_request_id,
        approved_by=admin_user.id,
        request_id=request_id
    )
    
    # Get document attachments with URLs
    document_service = DocumentService(db)
    attachments = []
    if role_request.attachments:
        file_id_strings = [str(att) for att in role_request.attachments]
        documents = document_service.get_documents_by_file_ids_admin(file_id_strings)
        docs_with_urls = document_service.get_documents_with_urls(documents, expires_in=3600)
        attachments = [
            DocumentAttachmentResponse(**doc_data) 
            for doc_data in docs_with_urls
        ]
    
    logger.info(
        "admin_role_request_approved",
        admin_user_id=admin_user.id,
        role_request_id=role_request_id
    )
    
    return AdminRoleRequestResponse(
        id=role_request.id,
        user_id=role_request.user_id,
        requested_roles=role_request.requested_roles,
        status=role_request.status,
        requested_at=role_request.requested_at,
        reviewed_by=role_request.reviewed_by,
        reviewed_at=role_request.reviewed_at,
        notes=role_request.notes,
        attachments=attachments,
        trust_score=role_request.trust_score
    )


@router.post(
    "/role-requests/{role_request_id}/reject",
    response_model=AdminRoleRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject role request (admin only)",
    response_description="Rejected role request"
)
async def reject_role_request(
    role_request_id: int,
    reject_data: Optional[RoleRequestRejectRequest] = Body(None),
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
    
    reason = reject_data.reason if reject_data else None
    
    role_granting_service = RoleGrantingService(db)
    role_request = role_granting_service.reject_role_request(
        role_request_id=role_request_id,
        rejected_by=admin_user.id,
        reason=reason,
        request_id=request_id
    )
    
    # Get document attachments with URLs
    document_service = DocumentService(db)
    attachments = []
    if role_request.attachments:
        file_id_strings = [str(att) for att in role_request.attachments]
        documents = document_service.get_documents_by_file_ids_admin(file_id_strings)
        docs_with_urls = document_service.get_documents_with_urls(documents, expires_in=3600)
        attachments = [
            DocumentAttachmentResponse(**doc_data) 
            for doc_data in docs_with_urls
        ]
    
    logger.info(
        "admin_role_request_rejected",
        admin_user_id=admin_user.id,
        role_request_id=role_request_id,
        has_reason=reason is not None
    )
    
    return AdminRoleRequestResponse(
        id=role_request.id,
        user_id=role_request.user_id,
        requested_roles=role_request.requested_roles,
        status=role_request.status,
        requested_at=role_request.requested_at,
        reviewed_by=role_request.reviewed_by,
        reviewed_at=role_request.reviewed_at,
        notes=role_request.notes,
        attachments=attachments,
        trust_score=role_request.trust_score
    )


# ------------------- Admin Application Routes ------------------- #

@router.get(
    "/applications",
    response_model=List[ApplicationResponse],
    summary="Get all applications (admin only)",
    response_description="List of all applications in the system"
)
async def get_all_applications(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get all applications in the system.
    
    **Admin-only endpoint** - Read-only access for monitoring and audit purposes.
    """
    service = ApplicationService(db)
    apps = service.get_all_applications()
    return [ApplicationResponse.model_validate(a) for a in apps]


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationResponse,
    summary="Get application by ID (admin only)",
    response_description="Application details"
)
async def get_admin_application(
    application_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific application by ID.
    
    **Admin-only endpoint** - Read-only access for monitoring and audit purposes.
    """
    service = ApplicationService(db)
    app = service.get_application_by_id(application_id)
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    return ApplicationResponse.model_validate(app)

