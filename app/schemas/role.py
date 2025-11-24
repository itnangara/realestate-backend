"""
Schemas for Role and UserRole
"""

from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    pass


class RoleResponse(RoleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class UserRoleResponse(BaseModel):
    role: RoleResponse

    model_config = ConfigDict(from_attributes=True)


class RoleListResponse(BaseModel):
    """Schema for role listing response"""
    id: int
    name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
