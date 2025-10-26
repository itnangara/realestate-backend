"""
Property model for real estate listings
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, Enum, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base
import enum
import os

class PropertyType(str, enum.Enum):
    """Property types enum - comprehensive real estate types"""
    HOUSE = "house"
    APARTMENT = "apartment"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    LAND = "land"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    DUPLEX = "duplex"
    RETAIL = "retail"
    OFFICE = "office"
    WAREHOUSE = "warehouse"

class PropertyStatus(str, enum.Enum):
    """Property status enum - simplified real-world statuses"""
    FOR_SALE = "for_sale"
    FOR_RENT = "for_rent"
    SOLD = "sold"
    RENTED = "rented"
    PENDING = "pending"
    DRAFT = "draft"
    OFF_MARKET = "off_market"


class Property(Base):
    """
    Industry-standard Property model for real estate application
    
    Features:
    - Comprehensive property types and statuses
    - Detailed location information with geocoding
    - Flexible pricing (sale, rent, both)
    - Rich property features and amenities
    - Media management (images, videos, documents)
    - SEO and marketing features
    - Analytics and tracking
    """
    __tablename__ = "properties"

    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Property classification
    property_type = Column(Enum(PropertyType), nullable=False, index=True)
    status = Column(Enum(PropertyStatus), default=PropertyStatus.DRAFT, nullable=False, index=True)
    
    # Location - comprehensive address system
    address = Column(String(500), nullable=False)
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(100), nullable=False, index=True)
    zip_code = Column(String(20), nullable=False, index=True)
    country = Column(String(100), default="USA", nullable=False)
    neighborhood = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True, index=True)
    longitude = Column(Float, nullable=True, index=True)
    
    # Property specifications
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Float, nullable=True)
    square_feet = Column(Integer, nullable=True)
    lot_size = Column(Float, nullable=True)  # in acres
    year_built = Column(Integer, nullable=True)
    stories = Column(Integer, nullable=True)
    garage_spaces = Column(Integer, nullable=True)
    
    # Pricing - flexible pricing system
    price = Column(Float, nullable=True)  # Sale price
    rent_price = Column(Float, nullable=True)  # Monthly rent
    price_per_sqft = Column(Float, nullable=True)
    hoa_fees = Column(Float, nullable=True)  # HOA monthly fees
    property_tax = Column(Float, nullable=True)  # Annual property tax
    
    # Features and amenities - lists (JSON for cross-database compatibility
    features = Column(JSON, nullable=True)  # Flexible features array
    amenities = Column(JSON, nullable=True)  # Flexible amenities array
    
    # Core boolean features only (derived from JSON features)
    is_furnished = Column(Boolean, default=False)
    pet_friendly = Column(Boolean, default=False)
    
    # Media and documents
    main_image_url = Column(String(500), nullable=True)
    images = Column(JSON, nullable=True)  # Array of image objects with metadata
    videos = Column(JSON, nullable=True)  # Array of video URLs
    documents = Column(JSON, nullable=True)  # Array of document URLs (floor plans, etc.)
    virtual_tour_url = Column(String(500), nullable=True)
    
    # Basic analytics (keep lean)
    views_count = Column(Integer, default=0, nullable=False)
    
    # Status and visibility
    is_featured = Column(Boolean, default=False, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_premium = Column(Boolean, default=False, nullable=False)
    featured_until = Column(DateTime(timezone=True), nullable=True)
    
    # Basic availability
    available_from = Column(DateTime(timezone=True), nullable=True)
    
    # Audit trail
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    # Foreign keys
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], back_populates="properties")
    agent = relationship("User", foreign_keys=[agent_id])
    applications = relationship("Application", back_populates="property")
    favorites = relationship("Favorite", back_populates="property")

    def __repr__(self):
        return f"<Property(id={self.id}, title='{self.title}', type='{self.property_type}')>"
    
    @property
    def full_address(self) -> str:
        """Get complete address string"""
        return f"{self.address}, {self.city}, {self.state} {self.zip_code}"
    
    @property
    def is_for_sale(self) -> bool:
        """Check if property is for sale"""
        return self.status in [PropertyStatus.FOR_SALE, PropertyStatus.PENDING]
    
    @property
    def is_for_rent(self) -> bool:
        """Check if property is for rent"""
        return self.status in [PropertyStatus.FOR_RENT, PropertyStatus.PENDING]
    
    @property
    def display_price(self) -> str:
        """Get formatted display price"""
        if self.price:
            return f"${self.price:,.0f}"
        elif self.rent_price:
            return f"${self.rent_price:,.0f}/month"
        return "Price on request"
    
    # Computed properties - derive from JSON features
    @property
    def has_garage(self) -> bool:
        """Check if property has garage from features"""
        return "garage" in (self.features or [])
    
    @property
    def has_pool(self) -> bool:
        """Check if property has pool from features"""
        return "pool" in (self.features or [])
    
    @property
    def has_garden(self) -> bool:
        """Check if property has garden from features"""
        return "garden" in (self.features or [])
    
    @property
    def has_balcony(self) -> bool:
        """Check if property has balcony from features"""
        return "balcony" in (self.features or [])
    
    @property
    def has_parking(self) -> bool:
        """Check if property has parking from features"""
        return "parking" in (self.features or [])
    
    @property
    def has_air_conditioning(self) -> bool:
        """Check if property has air conditioning from features"""
        return "air_conditioning" in (self.features or [])
    
    @property
    def has_heating(self) -> bool:
        """Check if property has heating from features"""
        return "heating" in (self.features or [])
    
    @property
    def has_garage(self) -> bool:
        """Check if property has garage from features"""
        return "garage" in (self.features or [])
    
    @property
    def has_pool(self) -> bool:
        """Check if property has pool from features"""
        return "pool" in (self.features or [])
    
    @property
    def has_garden(self) -> bool:
        """Check if property has garden from features"""
        return "garden" in (self.features or [])
    
    @property
    def has_balcony(self) -> bool:
        """Check if property has balcony from features"""
        return "balcony" in (self.features or [])
