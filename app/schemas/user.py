# app/schemas/user.py
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, EmailStr, Field, validator
from datetime import datetime
from app.models.user import UserRoles


class UserCreate(BaseModel):
    """Schema for creating a user"""
    email: EmailStr
    username: str = Field(min_length=3)
    password: str = Field(min_length=8)
    first_name: str
    last_name: str
    phone: Optional[str] = None
    roles: List[str] = Field(default_factory=list, description="List of user roles")

    model_config = {"extra": "forbid"}
    
    @validator('roles')
    def validate_roles(cls, v):
        """Validate that all roles are from allowed UserRoles"""
        if not v:
            return v
        allowed_roles = UserRoles.ALL_ROLES
        for role in v:
            if role not in allowed_roles:
                raise ValueError(f'Invalid role: {role}. Allowed roles: {allowed_roles}')
        return v


class UserUpdate(BaseModel):
    """Schema for updating a user - only includes actual user table columns"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    profile_image_url: Optional[str] = None
    company_name: Optional[str] = None
    license_number: Optional[str] = None
    bio: Optional[str] = None
    preferred_locations: Optional[List[str]] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    property_preferences: Optional[dict] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    is_premium: Optional[bool] = None
    roles: Optional[List[str]] = Field(None, description="List of role names to assign")

    model_config = {"extra": "forbid"}  # keep strict, only allow declared fields
    
    @validator('roles')
    def validate_roles(cls, v):
        """Validate that all roles are from allowed UserRoles"""
        if not v:
            return v
        allowed_roles = UserRoles.ALL_ROLES
        for role in v:
            if role not in allowed_roles:
                raise ValueError(f'Invalid role: {role}. Allowed roles: {allowed_roles}')
        return v


class UserOut(BaseModel):
    """Schema for user response - matches User model exactly"""
    id: int
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    profile_image_url: Optional[str] = None
    
    # Multi-role support - simple string array like User model
    roles: List[str] = []
    
    # Status fields
    is_active: bool
    is_verified: bool
    is_premium: bool
    
    # Professional information
    company_name: Optional[str] = None
    license_number: Optional[str] = None
    bio: Optional[str] = None
    
    # Location and preferences
    preferred_locations: Optional[List[str]] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    property_preferences: Optional[dict] = None
    
    # Activity tracking
    last_login: Optional[datetime] = None
    login_count: int = 0
    email_verified_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Schema for JWT token response"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Schema for token data"""
    email: Optional[str] = None
