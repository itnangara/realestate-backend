"""
Property model for real estate listings
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, Enum, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base
import enum

class PropertyType(str, enum.Enum):
    """Property types enum"""
    HOUSE = "house"
    APARTMENT = "apartment"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    LAND = "land"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"

class PropertyStatus(str, enum.Enum):
    """Property status enum"""
    FOR_SALE = "for_sale"
    FOR_RENT = "for_rent"
    SOLD = "sold"
    RENTED = "rented"
    PENDING = "pending"
    DRAFT = "draft"

class Property(Base):
    """Property model"""
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    property_type = Column(Enum(PropertyType), nullable=False)
    status = Column(Enum(PropertyStatus), default=PropertyStatus.DRAFT)
    
    # Location
    address = Column(String(500), nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    zip_code = Column(String(20), nullable=False)
    country = Column(String(100), default="USA")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # Property details
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Float, nullable=True)
    square_feet = Column(Integer, nullable=True)
    lot_size = Column(Float, nullable=True)
    year_built = Column(Integer, nullable=True)
    
    # Pricing
    price = Column(Float, nullable=True)
    rent_price = Column(Float, nullable=True)
    price_per_sqft = Column(Float, nullable=True)
    
    # Features
    has_garage = Column(Boolean, default=False)
    has_pool = Column(Boolean, default=False)
    has_garden = Column(Boolean, default=False)
    has_balcony = Column(Boolean, default=False)
    is_furnished = Column(Boolean, default=False)
    pet_friendly = Column(Boolean, default=False)
    
    # Media
    main_image_url = Column(String(500), nullable=True)
    image_urls = Column(Text, nullable=True)  # JSON string of image URLs
    
    # Metadata
    is_featured = Column(Boolean, default=False)
    views_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Foreign keys
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], back_populates="properties")
    agent = relationship("User", foreign_keys=[agent_id])
    applications = relationship("Application", back_populates="property")
    favorites = relationship("Favorite", back_populates="property")

    def __repr__(self):
        return f"<Property(id={self.id}, title='{self.title}', type='{self.property_type}')>"
