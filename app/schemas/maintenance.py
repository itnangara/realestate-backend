"""
Maintenance schemas for API request/response validation
Enterprise-grade Pydantic models with proper validation
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from app.models.maintenance import MaintenanceStatus, MaintenancePriority, MaintenanceCategory


class MaintenanceAttachmentBase(BaseModel):
    """Base attachment schema"""
    file_url: str = Field(..., description="File URL (S3 or file path)")
    file_type: Optional[str] = Field(None, description="MIME type (e.g., image/jpeg)")
    file_name: Optional[str] = Field(None, description="Original filename")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    description: Optional[str] = Field(None, description="Optional description")


class MaintenanceAttachmentCreate(MaintenanceAttachmentBase):
    """Schema for creating an attachment"""
    pass


class MaintenanceAttachmentResponse(MaintenanceAttachmentBase):
    """Schema for attachment response"""
    id: int
    request_id: int
    uploaded_by_id: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


class MaintenanceStatusHistoryResponse(BaseModel):
    """Schema for status history response"""
    id: int
    request_id: int
    old_status: Optional[str]
    new_status: str
    changed_by_id: int
    changed_by_name: Optional[str] = None  # User's full name
    note: Optional[str]
    changed_at: datetime

    class Config:
        from_attributes = True


class MaintenanceActivityResponse(BaseModel):
    """Schema for activity response"""
    id: int
    request_id: int
    actor_id: int
    actor_name: Optional[str] = None  # User's full name
    action_type: str
    action_data: Optional[Dict[str, Any]] = None
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class MaintenanceRequestBase(BaseModel):
    """Base maintenance request schema"""
    property_id: int = Field(..., description="Property ID")
    unit_number: Optional[str] = Field(None, max_length=50, description="Unit number (for multi-unit properties)")
    title: str = Field(..., min_length=1, max_length=255, description="Request title")
    description: Optional[str] = Field(None, description="Detailed description")
    priority: MaintenancePriority = Field(MaintenancePriority.MEDIUM, description="Request priority")
    category: MaintenanceCategory = Field(MaintenanceCategory.GENERAL, description="Request category")
    access_instructions: Optional[str] = Field(None, description="Instructions for maintenance team entry (e.g., 'Please call before entering', 'Use spare key with manager')")
    preferred_date: Optional[datetime] = Field(None, description="Preferred date for maintenance visit")
    preferred_time: Optional[str] = Field(None, description="Preferred time window: Morning, Afternoon, or Evening")


class MaintenanceRequestCreate(MaintenanceRequestBase):
    """Schema for creating a maintenance request"""
    pass


class MaintenanceRequestUpdate(BaseModel):
    """Schema for updating a maintenance request (landlord/staff only)"""
    status: Optional[MaintenanceStatus] = Field(None, description="New status (must follow valid transitions)")
    priority: Optional[MaintenancePriority] = Field(None, description="Updated priority")
    assigned_staff_id: Optional[int] = Field(None, description="Assign to staff member")
    estimated_cost: Optional[Decimal] = Field(None, ge=0, description="Estimated cost")
    actual_cost: Optional[Decimal] = Field(None, ge=0, description="Actual cost")
    external_vendor_name: Optional[str] = Field(None, max_length=255, description="External vendor name")
    external_vendor_contact: Optional[str] = Field(None, max_length=255, description="External vendor contact")
    note: Optional[str] = Field(None, description="Note for status change or update")


class MaintenanceRequestAssign(BaseModel):
    """Schema for assigning a maintenance request"""
    assigned_staff_id: Optional[int] = Field(None, description="Assign to staff member (user ID)")
    external_vendor_name: Optional[str] = Field(None, max_length=255, description="External vendor name (if not staff)")
    external_vendor_contact: Optional[str] = Field(None, max_length=255, description="External vendor contact")
    note: Optional[str] = Field(None, description="Assignment notes/instructions")


class MaintenanceRequestResponse(MaintenanceRequestBase):
    """Schema for maintenance request response"""
    id: int
    tenant_id: int
    reported_by_id: int
    assigned_staff_id: Optional[int] = None
    status: MaintenanceStatus
    estimated_cost: Optional[Decimal] = None
    actual_cost: Optional[Decimal] = None
    cost_approved_by_id: Optional[int] = None
    external_vendor_name: Optional[str] = None
    external_vendor_contact: Optional[str] = None
    access_instructions: Optional[str] = None
    preferred_date: Optional[datetime] = None
    preferred_time: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_status_change: datetime
    is_active: bool
    
    # Related data
    property: Optional[Dict[str, Any]] = None  # Property details
    tenant: Optional[Dict[str, Any]] = None  # Tenant details
    assigned_staff: Optional[Dict[str, Any]] = None  # Staff details
    attachments: List[MaintenanceAttachmentResponse] = []
    status_history: List[MaintenanceStatusHistoryResponse] = []
    activities: List[MaintenanceActivityResponse] = []

    class Config:
        from_attributes = True


class MaintenanceRequestListResponse(BaseModel):
    """Schema for paginated maintenance request list"""
    items: List[MaintenanceRequestResponse]
    total: int
    page: int
    limit: int
    pages: int


class MaintenanceRequestSummary(BaseModel):
    """Schema for maintenance request summary statistics"""
    total: int
    reported: int
    reviewing: int
    assigned: int
    acknowledged: int
    in_progress: int
    completed: int
    verified: int
    closed: int
    reopened: int
    rejected: int
    cancelled: int
    overdue: int = 0  # Requests past SLA deadline (future enhancement)


class MaintenanceCommentCreate(BaseModel):
    """Schema for adding a comment/note to a maintenance request"""
    comment: str = Field(..., min_length=1, description="Comment text")
    is_internal: bool = Field(False, description="Internal note (not visible to tenant)")


class MaintenanceCommentResponse(BaseModel):
    """Schema for comment response"""
    id: int
    request_id: int
    comment: str
    is_internal: bool
    created_by_id: int
    created_by_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Staff-specific schemas
class StaffAcknowledgeRequest(BaseModel):
    """Schema for staff acknowledging a request"""
    note: Optional[str] = Field(None, description="Optional acknowledgment note")


class StaffStartRequest(BaseModel):
    """Schema for staff starting work on a request"""
    started_at: Optional[datetime] = Field(None, description="When work started (defaults to now)")


class StaffCompleteRequest(BaseModel):
    """Schema for staff completing a request"""
    actual_cost: Optional[Decimal] = Field(None, ge=0, description="Actual cost (requires manager approval)")
    note: Optional[str] = Field(None, description="Completion notes")
    completed_at: Optional[datetime] = Field(None, description="When work completed (defaults to now)")


class StaffNoteCreate(BaseModel):
    """Schema for staff adding a note to a request"""
    text: str = Field(..., min_length=1, description="Note text")


class StaffAssignedTaskResponse(BaseModel):
    """Schema for staff assigned task list item"""
    id: int
    title: str
    property_id: int
    property_name: Optional[str] = None
    unit_number: Optional[str] = None
    status: MaintenanceStatus
    priority: MaintenancePriority
    category: MaintenanceCategory
    preferred_date: Optional[datetime] = None
    created_at: datetime
    last_status_change: datetime

    class Config:
        from_attributes = True


class StaffAssignedTasksListResponse(BaseModel):
    """Schema for paginated staff assigned tasks list"""
    items: List[StaffAssignedTaskResponse]
    meta: Dict[str, Any] = Field(default_factory=dict)
