"""
Admin schemas for role request management

Enterprise-grade schemas for admin endpoints with document details and URLs.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from app.models.role_request import RoleRequestStatus


class DocumentAttachmentResponse(BaseModel):
    """Response schema for document attachment in admin role request view"""
    id: int = Field(..., description="Internal document ID")
    file_id: UUID = Field(..., description="Unique file identifier (UUID)")
    file_name: str = Field(..., description="Original file name")
    url: str = Field(..., description="Presigned URL for accessing the document")
    type: str = Field(..., description="Document type")
    size: int = Field(..., description="File size in bytes")
    status: str = Field(..., description="Document status")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    
    model_config = ConfigDict(from_attributes=True)


class AdminRoleRequestResponse(BaseModel):
    """Response schema for role request in admin view with document details"""
    id: int
    user_id: int
    requested_roles: List[str]
    status: RoleRequestStatus
    requested_at: datetime
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    notes: Optional[str] = None
    attachments: List[DocumentAttachmentResponse] = Field(default_factory=list, description="List of attached documents with URLs")
    trust_score: float
    
    model_config = ConfigDict(from_attributes=True)


class AdminRoleRequestListResponse(BaseModel):
    """Response schema for listing role requests in admin view"""
    requests: List[AdminRoleRequestResponse] = Field(default_factory=list, description="List of role requests")
    total: int = Field(default=0, description="Total count of role requests")


class RoleRequestRejectRequest(BaseModel):
    """Request schema for rejecting a role request"""
    reason: Optional[str] = Field(None, max_length=1000, description="Optional rejection reason")




