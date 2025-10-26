"""
Seller Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class SellerBase(BaseModel):
    """Base seller schema"""
    name: str = Field(..., description="Seller's full name", min_length=1, max_length=200)
    age: Optional[int] = Field(None, description="Seller's age", ge=0, le=150)
    is_old: bool = Field(default=False, description="Whether the seller is considered old")

class SellerCreate(SellerBase):
    """Schema for creating a seller"""
    pass

class SellerUpdate(BaseModel):
    """Schema for updating a seller"""
    name: Optional[str] = Field(None, description="Seller's full name", min_length=1, max_length=200)
    age: Optional[int] = Field(None, description="Seller's age", ge=0, le=150)
    is_old: Optional[bool] = Field(None, description="Whether the seller is considered old")

class SellerResponse(SellerBase):
    """Schema for seller response"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class SellerDetailResponse(SellerResponse):
    """Schema for seller with additional details"""
    properties_count: Optional[int] = Field(None, description="Number of properties owned by this seller")
