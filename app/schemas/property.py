"""
Property Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, validator, root_validator, ConfigDict, Field, conint, confloat, model_validator, computed_field
from typing import Optional, List
from datetime import datetime
from app.models.property import PropertyType, PropertyStatus, ListingType

class PropertyBase(BaseModel):
    """Base property schema"""
    title: str = Field(..., min_length=1, description="Property title (required)")
    description: str = Field(..., min_length=1, description="Property description (required)")
    property_type: PropertyType
    listing_type: Optional[ListingType] = None
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
    listing_type: Optional[ListingType] = None
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
    is_owner: bool = False  # Computed: True if current user owns this property (via user_properties with LANDLORD relationship)
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Computed properties - automatically read from @property methods
    has_garage: bool = False
    has_pool: bool = False
    has_garden: bool = False
    has_balcony: bool = False
    
    @computed_field
    @property
    def display_price(self) -> Optional[float]:
        """
        Enterprise-grade computed field: Automatically selects the correct price based on listing_type.
        
        Rules:
        - FOR_RENT, FOR_LEASE → returns rent_price (monthly rent)
        - FOR_SALE, FOR_AUCTION, FOR_PORTFOLIO → returns price (sale price)
        - None/unknown listing_type → returns price as fallback
        
        This ensures single source of truth and eliminates frontend conditional logic.
        """
        if self.listing_type in [ListingType.FOR_RENT, ListingType.FOR_LEASE]:
            return self.rent_price
        # FOR_SALE, FOR_AUCTION, FOR_PORTFOLIO, or None → use sale price
        return self.price

    model_config = ConfigDict(from_attributes=True)

# --- Production-Grade Advanced Search Schemas ---

class PropertySearchFilters(BaseModel):
    """Production-grade property search filters with strict validation"""
    # Price filters
    price_min: Optional[conint(ge=0)] = Field(None, description="Minimum price")
    price_max: Optional[conint(ge=0)] = Field(None, description="Maximum price")
    
    # Property details
    property_type: Optional[PropertyType] = Field(None, description="Property type")
    bedrooms: Optional[conint(ge=0)] = Field(None, description="Minimum bedrooms")
    bathrooms: Optional[confloat(ge=0)] = Field(None, description="Minimum bathrooms")
    square_feet_min: Optional[conint(ge=0)] = Field(None, description="Minimum square feet")
    square_feet_max: Optional[conint(ge=0)] = Field(None, description="Maximum square feet")
    
    # Location filters
    city: Optional[str] = Field(None, description="City name")
    state: Optional[str] = Field(None, description="State")
    zip_code: Optional[str] = Field(None, description="ZIP code")
    country: Optional[str] = Field(None, description="Country")
    
    # Features filter
    features: Optional[str] = Field(None, description="Comma-separated list of features")
    
    # Listing type & status filters
    listing_type: Optional[ListingType] = Field(None, description="Listing type (for_sale, for_rent, etc.) - single value for backward compatibility")
    listing_types: Optional[List[ListingType]] = Field(None, description="List of listing types (for_sale, for_rent, etc.) - supports multiple values with OR logic")
    status: Optional[PropertyStatus] = Field(None, description="Property status")
    is_featured: Optional[bool] = Field(None, description="Featured properties only")
    year_built_min: Optional[conint(ge=1800, le=2030)] = Field(None, description="Minimum year built")
    year_built_max: Optional[conint(ge=1800, le=2030)] = Field(None, description="Maximum year built")
    
    # Pagination & Sorting
    page: conint(ge=1) = Field(1, description="Page number")
    limit: conint(ge=1, le=100) = Field(20, description="Items per page")
    sort_by: str = Field("created_at", description="Sort field")
    sort_order: str = Field("desc", description="Sort order: asc or desc")
    
    @model_validator(mode='after')
    def validate_listing_type_exclusivity(self):
        """Ensure listing_type and listing_types are not both provided"""
        if self.listing_type is not None and self.listing_types is not None:
            raise ValueError("Cannot use both 'listing_type' and 'listing_types'. Use 'listing_types' for multiple values.")
        return self

class PropertySearchResponse(BaseModel):
    """Response schema for property search results"""
    properties: List[PropertyResponse]
    total_count: int
    page: int
    limit: int
    total_pages: int
    
    model_config = ConfigDict(from_attributes=True)

# Legacy search schema (keeping for backward compatibility)
class PropertySearch(BaseModel):
    """Schema for property search filters"""
    city: Optional[str] = None
    state: Optional[str] = None
    property_type: Optional[PropertyType] = None
    listing_type: Optional[ListingType] = None
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


