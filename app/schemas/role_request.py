"""
Role Request schemas for API requests and responses
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
from app.models.role_request import RoleRequestStatus


class RoleRequestCreate(BaseModel):
    """Request schema for creating a role request"""
    requested_roles: List[str] = Field(..., min_items=1, description="List of roles to request")
    document_ids: Optional[List[int]] = Field(default=None, description="List of document IDs to attach")
    notes: Optional[str] = Field(default=None, max_length=1000, description="Optional notes for the request")
    
    @field_validator('requested_roles')
    @classmethod
    def validate_roles(cls, v: List[str]) -> List[str]:
        """Validate that requested roles are valid"""
        valid_roles = ["seller", "agent", "landlord", "investor", "tenant"]
        invalid_roles = [role for role in v if role not in valid_roles]
        if invalid_roles:
            raise ValueError(f"Invalid roles: {invalid_roles}. Valid roles are: {', '.join(valid_roles)}")
        if "buyer" in v:
            raise ValueError("Buyer role is assigned by default and cannot be requested")
        if "admin" in v:
            raise ValueError("Admin role cannot be requested through this endpoint")
        return v


class RoleRequestResponse(BaseModel):
    """Response schema for role request"""
    id: int
    user_id: int
    requested_roles: List[str]
    status: RoleRequestStatus
    requested_at: datetime
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    notes: Optional[str] = None
    attachments: Optional[List[int]] = None
    trust_score: float
    
    class Config:
        from_attributes = True


class RoleRequestListResponse(BaseModel):
    """Response schema for listing role requests"""
    requests: List[RoleRequestResponse]
    total: int

