"""
Favorite Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

# Import PropertyResponse for the relationship
from app.schemas.property import PropertyResponse

class FavoriteBase(BaseModel):
    """Base favorite schema"""
    pass

class FavoriteCreate(FavoriteBase):
    """Schema for creating a favorite"""
    property_id: int = Field(..., description="ID of the property to favorite")

class FavoriteResponse(FavoriteBase):
    """Schema for favorite response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    property_id: int
    created_at: datetime

class FavoriteDetailResponse(FavoriteResponse):
    """Schema for favorite with property details"""
    property: Optional[PropertyResponse] = Field(None, description="Property details")

class FavoriteCheckResponse(BaseModel):
    """Schema for favorite check response"""
    is_favorite: bool = Field(..., description="Whether the property is favorited by the user")