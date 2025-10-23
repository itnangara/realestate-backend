"""
Application model for property applications
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base
import enum

class ApplicationStatus(str, enum.Enum):
    """Application status enum"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    UNDER_REVIEW = "under_review"

class Application(Base):
    """Application model"""
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)
    
    # Application details
    message = Column(Text, nullable=True)
    move_in_date = Column(DateTime, nullable=True)
    lease_duration = Column(Integer, nullable=True)  # in months
    
    # Financial information
    annual_income = Column(Integer, nullable=True)
    credit_score = Column(Integer, nullable=True)
    employment_status = Column(String(100), nullable=True)
    employer_name = Column(String(200), nullable=True)
    
    # Contact information
    phone = Column(String(20), nullable=True)
    alternate_email = Column(String(255), nullable=True)
    
    # Documents
    documents_urls = Column(Text, nullable=True)  # JSON string of document URLs
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Foreign keys
    applicant_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    
    # Relationships
    applicant = relationship("User", back_populates="applications")
    property = relationship("Property", back_populates="applications")

    def __repr__(self):
        return f"<Application(id={self.id}, status='{self.status}', property_id={self.property_id})>"


