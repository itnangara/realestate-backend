"""
Tenant profile model for users with tenant role
"""

from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class TenantProfile(Base):
    """Tenant profile model"""
    __tablename__ = "tenant_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Employment & Income
    employment_status = Column(String(50), nullable=True)  # employed, self_employed, student, unemployed
    employer_name = Column(String(200), nullable=True)
    job_title = Column(String(100), nullable=True)
    annual_income = Column(Float, nullable=True)
    monthly_income = Column(Float, nullable=True)
    income_verification_documents = Column(Text, nullable=True)  # JSON array of document URLs
    
    # Financial Information
    credit_score = Column(Integer, nullable=True)
    credit_score_date = Column(DateTime(timezone=True), nullable=True)
    bank_name = Column(String(100), nullable=True)
    bank_account_type = Column(String(50), nullable=True)  # checking, savings, etc.
    
    # Rental History
    previous_landlord_name = Column(String(200), nullable=True)
    previous_landlord_phone = Column(String(20), nullable=True)
    previous_rent_amount = Column(Float, nullable=True)
    rental_history_years = Column(Float, nullable=True)
    eviction_history = Column(Boolean, default=False)
    references = Column(Text, nullable=True)  # JSON array of references
    
    # Preferences
    preferred_lease_duration = Column(Integer, nullable=True)  # months
    pet_owner = Column(Boolean, default=False)
    smoking = Column(Boolean, default=False)
    max_rent_budget = Column(Float, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="tenant_profile")

    def __repr__(self):
        return f"<TenantProfile(user_id={self.user_id}, employment_status='{self.employment_status}')>"
