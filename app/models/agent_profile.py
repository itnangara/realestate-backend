"""
Agent profile model for users with agent role
"""

from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class AgentProfile(Base):
    """Agent profile model"""
    __tablename__ = "agent_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Professional Information
    license_number = Column(String(100), nullable=False, unique=True)
    license_state = Column(String(50), nullable=False)
    license_expiry = Column(DateTime(timezone=True), nullable=True)
    license_type = Column(String(50), nullable=True)  # sales, broker, associate
    
    # Agency Information
    agency_name = Column(String(200), nullable=True)
    agency_license = Column(String(100), nullable=True)
    agency_phone = Column(String(20), nullable=True)
    agency_address = Column(Text, nullable=True)
    broker_name = Column(String(100), nullable=True)
    broker_license = Column(String(100), nullable=True)
    
    # Professional Details
    years_experience = Column(Integer, default=0)
    specializations = Column(JSON, nullable=True)  # Array of specializations
    service_areas = Column(JSON, nullable=True)  # Array of zip codes or areas
    languages_spoken = Column(JSON, nullable=True)  # Array of languages
    
    # Performance Metrics
    total_sales = Column(Integer, default=0)
    total_volume = Column(Float, default=0.0)
    average_sale_price = Column(Float, nullable=True)
    client_satisfaction_rating = Column(Float, nullable=True)
    response_time_hours = Column(Float, nullable=True)
    
    # Certifications & Awards
    certifications = Column(JSON, nullable=True)  # Array of certifications
    awards = Column(JSON, nullable=True)  # Array of awards
    professional_memberships = Column(JSON, nullable=True)  # Array of memberships
    
    # Contact & Availability
    office_phone = Column(String(20), nullable=True)
    mobile_phone = Column(String(20), nullable=True)
    website = Column(String(200), nullable=True)
    linkedin_profile = Column(String(200), nullable=True)
    availability_hours = Column(Text, nullable=True)  # JSON object with schedule
    
    # Commission & Fees
    commission_rate = Column(Float, nullable=True)  # Percentage
    minimum_commission = Column(Float, nullable=True)
    fee_structure = Column(Text, nullable=True)  # JSON object with fee details
    
    # Status & Verification
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    verification_date = Column(DateTime(timezone=True), nullable=True)
    background_check_date = Column(DateTime(timezone=True), nullable=True)
    insurance_expiry = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="agent_profile")

    def __repr__(self):
        return f"<AgentProfile(user_id={self.user_id}, license_number='{self.license_number}')>"
