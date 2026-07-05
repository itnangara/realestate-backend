"""
Maintenance routes for property maintenance request management
Enterprise-grade routes with role-based access control
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import math

from app.utils.database import get_db
from app.schemas.maintenance import (
    MaintenanceRequestCreate, MaintenanceRequestUpdate, MaintenanceRequestResponse,
    MaintenanceRequestListResponse, MaintenanceRequestAssign, MaintenanceRequestSummary,
    StaffUserSchema,
    MaintenanceAttachmentCreate, MaintenanceCommentCreate
)
from app.services.maintenance_service import MaintenanceService
from app.models.maintenance import MaintenanceStatus, MaintenancePriority, MaintenanceCategory
from app.dependencies.user_dependencies import get_current_user, get_current_landlord_user
from app.models.user import User
from app.core.logger import get_logger

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])
logger = get_logger(__name__)


@router.post(
    "",
    response_model=MaintenanceRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create maintenance request",
    response_description="Created maintenance request in REPORTED status"
)
async def create_maintenance_request(
    request_data: MaintenanceRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new maintenance request.
    
    **Enterprise-grade business rules:**
    - Only tenants can create requests
    - Property must exist and be accessible
    - Request starts in REPORTED status
    - Emergency priority triggers immediate notification (future enhancement)
    """
    if not current_user.has_role("tenant"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenants can create maintenance requests"
        )
    
    service = MaintenanceService(db)
    request = service.create_request(request_data, current_user.id, current_user.id)
    
    # Load relationships for response
    db.refresh(request)
    
    # Build response with related data
    response_data = _build_request_response(request, db)
    
    return MaintenanceRequestResponse(**response_data)


@router.post(
    "/{request_id}/attachments",
    response_model=MaintenanceRequestResponse,
    summary="Upload attachments to maintenance request",
    response_description="Uploaded attachments added to maintenance request"
)
async def upload_maintenance_attachments(
    request_id: int,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload attachments (photos/videos) to a maintenance request.
    
    **Business Rules:**
    - Only tenant who created the request or landlord/staff can upload
    - Maximum file size: 10MB per file
    - Allowed types: images (jpeg, png, webp) and videos (mp4, mov)
    - Files are uploaded to S3 and URLs stored in database
    """
    from app.models.maintenance import MaintenanceAttachment
    from app.services.s3_service import s3_service
    import uuid
    from pathlib import Path
    import boto3
    from botocore.exceptions import ClientError
    from decouple import config
    
    # Get request and verify access
    service = MaintenanceService(db)
    request = service.get_request(request_id, current_user)
    
    # Validate files
    max_size = 10 * 1024 * 1024  # 10MB
    allowed_types = [
        "image/jpeg", "image/jpg", "image/png", "image/webp",
        "video/mp4", "video/quicktime", "video/x-msvideo"
    ]
    
    uploaded_attachments = []
    errors = []
    
    # Initialize S3 client for direct upload
    s3_client = None
    bucket_name = config("AWS_BUCKET_NAME", default=None)
    if bucket_name:
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=config("AWS_ACCESS_KEY_ID", default=None),
                aws_secret_access_key=config("AWS_SECRET_ACCESS_KEY", default=None),
                region_name=config("AWS_REGION", default="us-east-1")
            )
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {str(e)}")
    
    for file in files:
        # Validate file size
        file_content = await file.read()
        file_size = len(file_content)
        
        if file_size > max_size:
            errors.append(f"{file.filename}: File size exceeds 10MB limit")
            continue
        
        if file.content_type not in allowed_types:
            errors.append(f"{file.filename}: File type not allowed. Allowed: images (jpeg, png, webp) and videos (mp4, mov)")
            continue
        
        try:
            # Generate S3 key
            file_extension = Path(file.filename).suffix if file.filename else '.bin'
            s3_key = f"maintenance/{request_id}/{uuid.uuid4()}{file_extension}"
            
            # Upload to S3 directly
            if s3_client and bucket_name:
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=s3_key,
                    Body=file_content,
                    ContentType=file.content_type
                )
                # Generate public URL
                file_url = f"https://{bucket_name}.s3.{config('AWS_REGION', default='us-east-1')}.amazonaws.com/{s3_key}"
            else:
                # Fallback: store file path if S3 not configured
                logger.warning("S3 not configured, storing file path only")
                file_url = s3_key
            
            # Create attachment record
            attachment = MaintenanceAttachment(
                request_id=request_id,
                uploaded_by_id=current_user.id,
                file_url=file_url,
                file_type=file.content_type,
                file_name=file.filename,
                file_size=file_size
            )
            db.add(attachment)
            uploaded_attachments.append(attachment)
            
        except Exception as e:
            logger.error(f"Error uploading attachment {file.filename}: {str(e)}", exc_info=True)
            errors.append(f"{file.filename}: Upload failed - {str(e)}")
    
    if errors and not uploaded_attachments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": errors, "message": "All file uploads failed"}
        )
    
    db.commit()
    
    # Refresh request to get updated attachments
    db.refresh(request)
    response_data = _build_request_response(request, db)
    
    if errors:
        logger.warning(
            "partial_attachment_upload",
            request_id=request_id,
            successful=len(uploaded_attachments),
            failed=len(errors),
            errors=errors
        )
    
    return MaintenanceRequestResponse(**response_data)


def get_maintenance_service(db: Session = Depends(get_db)):
    """Provides a MaintenanceService instance with a database session."""
    return MaintenanceService(db)

@router.get(
    "/staff",
    response_model=List[StaffUserSchema],
    status_code=status.HTTP_200_OK,
)
def get_maintenance_staff(
    current_user: User=Depends(get_current_landlord_user),
    service: MaintenanceService = Depends(get_maintenance_service)
):
    """
    Retrieves the list of available maintenance staff for assignment.
    Accessible by Landlords and Property Managers.
    """
    # The service layer must now filter the staff list based on the properties managed by current_user.
    return service.get_maintenance_staff_scoped_by_landlord(landlord_id=current_user.id)
    

@router.get(
    "",
    response_model=MaintenanceRequestListResponse,
    summary="List maintenance requests",
    response_description="Paginated list of maintenance requests with filters and status counts"
)
async def list_maintenance_requests(
    status: Optional[MaintenanceStatus] = Query(None, description="Filter by status"),
    property_id: Optional[int] = Query(None, description="Filter by property ID"),
    priority: Optional[MaintenancePriority] = Query(None, description="Filter by priority"),
    category: Optional[MaintenanceCategory] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search by title, description, or unit number"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List maintenance requests with role-based filtering and dynamic status counts.
    """
    service = MaintenanceService(db)
    
    requests, total, status_counts = service.list_requests(
        user=current_user,
        status=status,
        property_id=property_id,
        priority=priority,
        category=category,
        search=search,
        page=page,
        limit=limit
    )
    
    # Build response with related data
    items = [_build_request_response(req, db) for req in requests]
    
    pages = math.ceil(total / limit) if total > 0 else 0
    
    return MaintenanceRequestListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=pages,
        status_counts=status_counts
    )

@router.get(
    "/{request_id}",
    response_model=MaintenanceRequestResponse,
    summary="Get maintenance request by ID",
    response_description="Maintenance request details with full history"
)
async def get_maintenance_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get maintenance request details by ID.
    
    **Authorization:**
    - Tenant: Can only view their own requests
    - Landlord/Agent: Can view requests for their properties
    - Staff: Can view assigned requests
    """
    service = MaintenanceService(db)
    request = service.get_request(request_id, current_user)
    
    response_data = _build_request_response(request, db)
    
    return MaintenanceRequestResponse(**response_data)


@router.patch(
    "/{request_id}",
    response_model=MaintenanceRequestResponse,
    summary="Update maintenance request",
    response_description="Updated maintenance request"
)
async def update_maintenance_request(
    request_id: int,
    update_data: MaintenanceRequestUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update maintenance request details.
    
    **Business Rules:**
    - Landlords/agents can update priority, costs, assignment
    - Status updates must follow valid transitions
    - Tenants cannot update after creation
    """
    service = MaintenanceService(db)
    request = service.update_request(request_id, update_data, current_user)
    
    response_data = _build_request_response(request, db)
    
    return MaintenanceRequestResponse(**response_data)


@router.post(
    "/{request_id}/assign",
    response_model=MaintenanceRequestResponse,
    summary="Assign maintenance request",
    response_description="Assigned maintenance request"
)
async def assign_maintenance_request(
    request_id: int,
    assign_data: MaintenanceRequestAssign,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Assign a maintenance request to staff or vendor.
    
    **Business Rules:**
    - Only landlords/agents can assign
    - Can assign to staff member or external vendor
    - Automatically transitions to ASSIGNED status
    """
    service = MaintenanceService(db)
    request = service.assign_request(request_id, assign_data, current_user)
    
    response_data = _build_request_response(request, db)
    
    return MaintenanceRequestResponse(**response_data)


@router.post(
    "/{request_id}/status",
    response_model=MaintenanceRequestResponse,
    summary="Update maintenance request status",
    response_description="Updated maintenance request status"
)
async def update_maintenance_status(
    request_id: int,
    new_status: MaintenanceStatus = Query(..., description="New status"),
    note: Optional[str] = Query(None, description="Note for status change"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update maintenance request status.
    
    **Business Rules:**
    - Status transitions must be valid
    - Authorization checks based on role and current status
    - Creates status history and activity log entries
    """
    service = MaintenanceService(db)
    request = service.update_status(request_id, new_status, current_user, note)
    
    response_data = _build_request_response(request, db)
    
    return MaintenanceRequestResponse(**response_data)


@router.get(
    "/summary/stats",
    response_model=MaintenanceRequestSummary,
    summary="Get maintenance request summary",
    response_description="Summary statistics for maintenance requests"
)
async def get_maintenance_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get maintenance request summary statistics.
    
    **Role-based:**
    - Tenant: Statistics for their requests
    - Landlord/Agent: Statistics for their properties
    - Staff: Statistics for assigned requests
    """
    service = MaintenanceService(db)
    summary = service.get_summary(current_user)
    
    return MaintenanceRequestSummary(**summary)

def _build_request_response(request, db: Session) -> dict:
    """Helper function to build response with related data"""
    from app.models.property import Property
    from app.models.user import User
    
    # Load property
    property_obj = db.query(Property).filter(Property.id == request.property_id).first()
    property_data = None
    if property_obj:
        property_data = {
            "id": property_obj.id,
            "title": property_obj.title,
            "address": property_obj.address,
            "city": property_obj.city,
            "state": property_obj.state
        }
    
    # Load tenant
    tenant = db.query(User).filter(User.id == request.tenant_id).first()
    tenant_data = None
    if tenant:
        tenant_data = {
            "id": tenant.id,
            "first_name": tenant.first_name,
            "last_name": tenant.last_name,
            "email": tenant.email,
            "phone": tenant.phone
        }
    
    # Load assigned staff
    assigned_staff_data = None
    if request.assigned_staff_id:
        staff = db.query(User).filter(User.id == request.assigned_staff_id).first()
        if staff:
            assigned_staff_data = {
                "id": staff.id,
                "first_name": staff.first_name,
                "last_name": staff.last_name,
                "email": staff.email,
                "phone": staff.phone
            }
    
    # Build status history with user names
    status_history = []
    for history in request.status_history:
        changed_by = db.query(User).filter(User.id == history.changed_by_id).first()
        status_history.append({
            "id": history.id,
            "request_id": history.request_id,
            "old_status": history.old_status,
            "new_status": history.new_status,
            "changed_by_id": history.changed_by_id,
            "changed_by_name": f"{changed_by.first_name} {changed_by.last_name}" if changed_by else None,
            "note": history.note,
            "changed_at": history.changed_at
        })
    
    # Build activities with user names
    activities = []
    for activity in request.activities:
        actor = db.query(User).filter(User.id == activity.actor_id).first()
        activities.append({
            "id": activity.id,
            "request_id": activity.request_id,
            "actor_id": activity.actor_id,
            "actor_name": f"{actor.first_name} {actor.last_name}" if actor else None,
            "action_type": activity.action_type,
            "action_data": activity.action_data,
            "description": activity.description,
            "created_at": activity.created_at
        })
    
    # Build attachments
    attachments = []
    for attachment in request.attachments:
        attachments.append({
            "id": attachment.id,
            "request_id": attachment.request_id,
            "file_url": attachment.file_url,
            "file_type": attachment.file_type,
            "file_name": attachment.file_name,
            "file_size": attachment.file_size,
            "uploaded_by_id": attachment.uploaded_by_id,
            "description": attachment.description,
            "uploaded_at": attachment.uploaded_at
        })
    
    return {
        "id": request.id,
        "property_id": request.property_id,
        "unit_number": request.unit_number,
        "title": request.title,
        "description": request.description,
        "priority": request.priority,
        "category": request.category,
        "tenant_id": request.tenant_id,
        "reported_by_id": request.reported_by_id,
        "assigned_staff_id": request.assigned_staff_id,
        "status": request.status,
        "estimated_cost": request.estimated_cost,
        "actual_cost": request.actual_cost,
        "cost_approved_by_id": request.cost_approved_by_id,
        "external_vendor_name": request.external_vendor_name,
        "external_vendor_contact": request.external_vendor_contact,
        "access_instructions": request.access_instructions,
        "preferred_date": request.preferred_date,
        "preferred_time": request.preferred_time,
        "created_at": request.created_at,
        "updated_at": request.updated_at,
        "last_status_change": request.last_status_change,
        "is_active": request.is_active,
        "property": property_data,
        "tenant": tenant_data,
        "assigned_staff": assigned_staff_data,
        "attachments": attachments,
        "status_history": status_history,
        "activities": activities
    }
