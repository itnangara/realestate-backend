"""
Property Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, validator, root_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from app.models.property import PropertyType, PropertyStatus

class PropertyBase(BaseModel):
    """Base property schema"""
    title: str
    description: Optional[str] = None
    property_type: PropertyType
    status: PropertyStatus = PropertyStatus.DRAFT
    
    # Location
    address: str
    city: str
    state: str
    zip_code: str
    country: str = "USA"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Property details
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    square_feet: Optional[int] = None
    lot_size: Optional[float] = None
    year_built: Optional[int] = None
    
    # Pricing
    price: Optional[float] = None
    rent_price: Optional[float] = None
    
    # Features - only real database columns
    is_furnished: bool = False
    pet_friendly: bool = False

class PropertyCreate(PropertyBase):
    """Schema for creating a property"""
    pass

class PropertyUpdate(BaseModel):
    """Schema for updating a property"""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[PropertyStatus] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    square_feet: Optional[int] = None
    lot_size: Optional[float] = None
    year_built: Optional[int] = None
    price: Optional[float] = None
    rent_price: Optional[float] = None
    is_furnished: Optional[bool] = None
    pet_friendly: Optional[bool] = None
    main_image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None

class PropertyResponse(PropertyBase):
    """Schema for property response"""
    id: int
    price_per_sqft: Optional[float] = None
    main_image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None
    is_featured: bool = False
    views_count: int = 0
    is_active: bool = True
    owner_id: int
    agent_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Computed properties - automatically read from @property methods
    has_garage: bool = False
    has_pool: bool = False
    has_garden: bool = False
    has_balcony: bool = False

    model_config = ConfigDict(from_attributes=True)

class PropertySearch(BaseModel):
    """Schema for property search filters"""
    city: Optional[str] = None
    state: Optional[str] = None
    property_type: Optional[PropertyType] = None
    status: Optional[PropertyStatus] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_bedrooms: Optional[int] = None
    max_bedrooms: Optional[int] = None
    min_bathrooms: Optional[float] = None
    max_bathrooms: Optional[float] = None
    min_square_feet: Optional[int] = None
    max_square_feet: Optional[int] = None
    has_garage: Optional[bool] = None
    has_pool: Optional[bool] = None
    pet_friendly: Optional[bool] = None
    page: int = 1
    limit: int = 20


