"""
Schemas for Role and UserRole
"""

from pydantic import BaseModel
from typing import List, Optional


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    pass


class RoleResponse(RoleBase):
    id: int

    class Config:
        from_attributes = True


class UserRoleResponse(BaseModel):
    role: RoleResponse

    class Config:
        from_attributes = True


class RoleListResponse(BaseModel):
    """Schema for role listing response"""
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True
