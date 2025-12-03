"""
Maintenance Staff routes for staff-specific maintenance operations
Enterprise-grade routes with role-based access control for maintenance staff
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import math

from app.utils.database import get_db
from app.schemas.maintenance import (
    MaintenanceRequestResponse, StaffAssignedTaskResponse, StaffAssignedTasksListResponse,
    StaffAcknowledgeRequest, StaffStartRequest, StaffCompleteRequest, StaffNoteCreate,
    MaintenanceAttachmentResponse
)
from app.services.maintenance_service import MaintenanceService
from app.models.maintenance import MaintenanceStatus, MaintenancePriority, MaintenanceCategory
from app.dependencies.user_dependencies import get_current_user
from app.dependencies.authorization_dependencies import require_role, staff_scope_check
from app.models.user import User
from app.models.maintenance import MaintenanceRequest
from app.core.logger import get_logger

router = APIRouter(prefix="/maintenance/staff", tags=["Maintenance - Staff"])
logger = get_logger(__name__)


def _build_staff_task_response(request: MaintenanceRequest, db: Session) -> dict:
    """Build staff task response with minimal data for list view"""
    return {
        "id": request.id,
        "title": request.title,
        "property_id": request.property_id,
        "property_name": request.property.name if request.property else None,
        "unit_number": request.unit_number,
        "status": request.status,
        "priority": request.priority,
        "category": request.category,
        "preferred_date": request.preferred_date,
        "created_at": request.created_at,
        "last_status_change": request.last_status_change
    }


def _build_request_response(request: MaintenanceRequest, db: Session) -> dict:
    """Build full request response with related data"""
    # Import here to avoid circular dependency
    from app.routes.maintenance import _build_request_response
    return _build_request_response(request, db)


@router.get(
    "/assigned",
    response_model=StaffAssignedTasksListResponse,
    summary="List tasks assigned to current staff",
    response_description="Paginated list of maintenance requests assigned to the current staff member"
)
async def list_assigned_tasks(
    status: Optional[List[MaintenanceStatus]] = Query(None, description="Filter by status (can specify multiple)"),
    property_id: Optional[int] = Query(None, description="Filter by property ID"),
    priority: Optional[MaintenancePriority] = Query(None, description="Filter by priority"),
    category: Optional[MaintenanceCategory] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search by title, description, or unit number"),
    date_from: Optional[datetime] = Query(None, description="Filter by created date from"),
    date_to: Optional[datetime] = Query(None, description="Filter by created date to"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_role("maintenance_staff")),
    db: Session = Depends(get_db)
):
    """
    List maintenance requests assigned to the current staff member.
    
    **Enterprise-grade filtering:**
    - Only returns requests assigned to the current staff user
    - Supports multiple status filters
    - Date range filtering
    - Search by title, description, unit number
    - Pagination with metadata
    """
    service = MaintenanceService(db)
    requests, total = service.list_assigned(
        staff_user=current_user,
        status=status,
        property_id=property_id,
        priority=priority,
        category=category,
        search=search,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=page_size
    )
    
    # Build response items
    items = [StaffAssignedTaskResponse(**_build_staff_task_response(req, db)) for req in requests]
    
    pages = math.ceil(total / page_size) if total > 0 else 0
    
    return StaffAssignedTasksListResponse(
        items=items,
        meta={
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": pages
        }
    )


@router.get(
    "/{id}",
    response_model=MaintenanceRequestResponse,
    summary="Get task detail (staff-scoped)",
    response_description="Full maintenance request details for assigned task"
)
async def get_task_detail(
    id: int,
    current_user: User = Depends(require_role("maintenance_staff")),
    request: MaintenanceRequest = Depends(staff_scope_check),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a maintenance request assigned to the current staff member.
    
    **Authorization:**
    - Only returns requests assigned to the current staff user
    - Includes full request details, attachments, activities, and timeline
    """
    response_data = _build_request_response(request, db)
    return MaintenanceRequestResponse(**response_data)


@router.post(
    "/{id}/acknowledge",
    response_model=MaintenanceRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Acknowledge assigned task",
    response_description="Task acknowledged and status changed to ACKNOWLEDGED"
)
async def acknowledge_task(
    id: int,
    payload: StaffAcknowledgeRequest,
    current_user: User = Depends(require_role("maintenance_staff")),
    request: MaintenanceRequest = Depends(staff_scope_check),
    db: Session = Depends(get_db)
):
    """
    Acknowledge an assigned maintenance request.
    
    **Business Rules:**
    - Only assigned staff can acknowledge
    - Status must be ASSIGNED
    - Transitions to ACKNOWLEDGED
    - Creates status history and activity log entries
    """
    service = MaintenanceService(db)
    updated_request = service.acknowledge_request(
        request_id=id,
        staff_user=current_user,
        note=payload.note
    )
    
    response_data = _build_request_response(updated_request, db)
    return MaintenanceRequestResponse(**response_data)


@router.post(
    "/{id}/start",
    response_model=MaintenanceRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Start work on task",
    response_description="Task started and status changed to IN_PROGRESS"
)
async def start_task(
    id: int,
    payload: StaffStartRequest,
    current_user: User = Depends(require_role("maintenance_staff")),
    request: MaintenanceRequest = Depends(staff_scope_check),
    db: Session = Depends(get_db)
):
    """
    Start work on an acknowledged maintenance request.
    
    **Business Rules:**
    - Only assigned staff can start
    - Status must be ACKNOWLEDGED
    - Transitions to IN_PROGRESS
    - Creates status history and activity log entries
    """
    service = MaintenanceService(db)
    updated_request = service.start_request(
        request_id=id,
        staff_user=current_user,
        started_at=payload.started_at
    )
    
    response_data = _build_request_response(updated_request, db)
    return MaintenanceRequestResponse(**response_data)


@router.post(
    "/{id}/complete",
    response_model=MaintenanceRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark task as completed",
    response_description="Task completed and status changed to COMPLETED"
)
async def complete_task(
    id: int,
    payload: StaffCompleteRequest,
    current_user: User = Depends(require_role("maintenance_staff")),
    request: MaintenanceRequest = Depends(staff_scope_check),
    db: Session = Depends(get_db)
):
    """
    Mark a maintenance request as completed.
    
    **Business Rules:**
    - Only assigned staff can complete
    - Status must be IN_PROGRESS
    - Transitions to COMPLETED
    - Can include actual cost (requires manager approval)
    - Creates status history and activity log entries
    """
    from decimal import Decimal
    
    service = MaintenanceService(db)
    updated_request = service.complete_request(
        request_id=id,
        staff_user=current_user,
        actual_cost=Decimal(str(payload.actual_cost)) if payload.actual_cost is not None else None,
        note=payload.note,
        completed_at=payload.completed_at
    )
    
    response_data = _build_request_response(updated_request, db)
    return MaintenanceRequestResponse(**response_data)


@router.post(
    "/{id}/attachments",
    response_model=MaintenanceAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload attachment to task",
    response_description="Attachment uploaded and linked to maintenance request"
)
async def upload_attachment(
    id: int,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    current_user: User = Depends(require_role("maintenance_staff")),
    request: MaintenanceRequest = Depends(staff_scope_check),
    db: Session = Depends(get_db)
):
    """
    Upload an attachment (image, PDF, etc.) to a maintenance request.
    
    **Business Rules:**
    - Only assigned staff can upload attachments
    - File size and type validation (future enhancement)
    - Files stored to S3 or local storage
    - Creates MaintenanceAttachment record
    """
    # TODO: Implement file upload to S3
    # For now, return a placeholder response
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="File upload not yet implemented. Will integrate with S3 service."
    )


@router.post(
    "/{id}/notes",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Add note to task",
    response_description="Internal note added to maintenance request"
)
async def add_note(
    id: int,
    payload: StaffNoteCreate,
    current_user: User = Depends(require_role("maintenance_staff")),
    request: MaintenanceRequest = Depends(staff_scope_check),
    db: Session = Depends(get_db)
):
    """
    Add an internal note to a maintenance request.
    
    **Business Rules:**
    - Only assigned staff can add notes
    - Creates MaintenanceActivity entry with action_type "note"
    - Notes are visible in activity timeline
    """
    service = MaintenanceService(db)
    activity = service.add_note(
        request_id=id,
        staff_user=current_user,
        note_text=payload.text
    )
    
    return {
        "id": activity.id,
        "request_id": activity.request_id,
        "action_type": activity.action_type,
        "description": activity.description,
        "created_at": activity.created_at
    }

