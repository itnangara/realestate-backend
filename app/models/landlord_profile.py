"""
Landlord profile model for users with landlord role
"""

from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class LandlordProfile(Base):
    """Landlord profile model"""
    __tablename__ = "landlord_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Business Information
    business_name = Column(String(200), nullable=True)
    business_type = Column(String(50), nullable=True)  # individual, llc, corporation, partnership
    tax_id = Column(String(50), nullable=True)
    business_license = Column(String(100), nullable=True)
    
    # Banking Information
    bank_name = Column(String(100), nullable=True)
    bank_routing_number = Column(String(20), nullable=True)
    bank_account_number = Column(String(50), nullable=True)
    bank_account_type = Column(String(50), nullable=True)  # checking, savings, business
    
    # Property Management
    total_properties = Column(Integer, default=0)
    total_units = Column(Integer, default=0)
    properties_managed = Column(JSON, nullable=True)  # Array of property IDs
    management_company = Column(String(200), nullable=True)
    property_manager_name = Column(String(100), nullable=True)
    property_manager_phone = Column(String(20), nullable=True)
    
    # Financial Information
    annual_rental_income = Column(Float, nullable=True)
    monthly_rental_income = Column(Float, nullable=True)
    property_valuation = Column(Float, nullable=True)
    mortgage_balance = Column(Float, nullable=True)
    
    # Insurance & Legal
    insurance_company = Column(String(200), nullable=True)
    insurance_policy_number = Column(String(100), nullable=True)
    insurance_expiry = Column(DateTime(timezone=True), nullable=True)
    legal_entity_type = Column(String(50), nullable=True)
    
    # Preferences & Settings
    preferred_lease_terms = Column(Text, nullable=True)  # JSON object with terms
    pet_policy = Column(Text, nullable=True)
    smoking_policy = Column(Text, nullable=True)
    maintenance_preferences = Column(Text, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    verification_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="landlord_profile")

    def __repr__(self):
        return f"<LandlordProfile(user_id={self.user_id}, business_name='{self.business_name}')>"
