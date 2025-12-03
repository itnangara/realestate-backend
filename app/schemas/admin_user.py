"""
Admin User Management Schemas

Enterprise-grade Pydantic schemas for admin user management operations.
"""

from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from datetime import datetime
from app.models.user import UserRoles, UserStatus


class UserCreateAdmin(BaseModel):
    """Schema for admin creating a user"""
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: Optional[str] = Field(None, min_length=8, description="Password (optional - auto-generated if not provided)")
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    roles: List[str] = Field(default_factory=list, description="List of role names to assign")
    status: Optional[UserStatus] = Field(None, description="User status (defaults to PENDING)")
    is_active: Optional[bool] = Field(True, description="Whether user is active")
    is_verified: Optional[bool] = Field(False, description="Whether email is verified")
    property_ids: Optional[List[int]] = Field(None, description="Property IDs to assign (for maintenance_staff/landlord)")
    notes: Optional[str] = Field(None, description="Internal admin notes")
    
    model_config = ConfigDict(extra="forbid")
    
    @field_validator('roles')
    @classmethod
    def validate_roles(cls, v):
        """Validate that all roles are from allowed UserRoles"""
        if not v:
            return v
        allowed_roles = UserRoles.ALL_ROLES
        for role in v:
            if role not in allowed_roles:
                raise ValueError(f'Invalid role: {role}. Allowed roles: {allowed_roles}')
        return v


class UserUpdateAdmin(BaseModel):
    """Schema for admin updating a user"""
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    roles: Optional[List[str]] = Field(None, description="List of role names to assign")
    status: Optional[UserStatus] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    property_ids: Optional[List[int]] = Field(None, description="Property IDs to assign (replaces existing assignments)")
    notes: Optional[str] = None
    
    model_config = ConfigDict(extra="forbid")
    
    @field_validator('roles')
    @classmethod
    def validate_roles(cls, v):
        """Validate that all roles are from allowed UserRoles"""
        if not v:
            return v
        allowed_roles = UserRoles.ALL_ROLES
        for role in v:
            if role not in allowed_roles:
                raise ValueError(f'Invalid role: {role}. Allowed roles: {allowed_roles}')
        return v


class UserPropertyAssignment(BaseModel):
    """Schema for property assignment response"""
    property_id: int
    property_title: Optional[str] = None
    property_address: Optional[str] = None


class AuditLogEntry(BaseModel):
    """Schema for audit log entry"""
    id: int
    actor_id: Optional[int] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    meta: Optional[dict] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class UserDetailAdmin(BaseModel):
    """Schema for detailed user response (admin view)"""
    id: int
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    full_name: str
    phone: Optional[str] = None
    profile_image_url: Optional[str] = None
    
    # Roles
    roles: List[str] = []
    
    # Status fields
    status: UserStatus
    is_active: bool
    is_verified: bool
    is_premium: bool
    
    # Property assignments
    assigned_properties: List[UserPropertyAssignment] = []
    
    # Activity tracking
    last_login: Optional[datetime] = None
    login_count: int = 0
    email_verified_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class UserListItemAdmin(BaseModel):
    """Schema for user list item (simplified for table view)"""
    id: int
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    full_name: str
    phone: Optional[str] = None
    roles: List[str] = []
    status: UserStatus
    is_active: bool
    is_verified: bool
    last_login: Optional[datetime] = None
    assigned_properties_count: int = 0
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    """Schema for paginated user list response"""
    users: List[UserListItemAdmin]
    total: int
    page: int
    limit: int
    total_pages: int


class PasswordResetRequest(BaseModel):
    """Schema for password reset request"""
    new_password: str = Field(min_length=8, description="New password")
    send_email: Optional[bool] = Field(True, description="Whether to send password reset email")


class BulkActionRequest(BaseModel):
    """Schema for bulk actions"""
    user_ids: List[int] = Field(..., min_length=1, description="List of user IDs")
    action: str = Field(..., description="Action to perform (activate, deactivate, assign_properties)")
    property_ids: Optional[List[int]] = Field(None, description="Property IDs (required for assign_properties action)")

