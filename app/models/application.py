"""
Application model for property applications
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, Boolean, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON
from app.utils.database import Base
from datetime import datetime, timezone
import enum

class ApplicationStatus(str, enum.Enum):
    """Application status enum - clean modern workflow following industry standards
    
    Core flow: draft → submitted → reviewed → (approved | rejected | needs_info)
    Lease flow: approved → signed → active_lease → closed
    Withdrawal: any status → withdrawn
    """
    DRAFT = "draft"  # Tenant is still filling out the application
    SUBMITTED = "submitted"  # Tenant submitted, waiting for landlord to review (covers: pending, under_review, awaiting_decision, in_queue)
    REVIEWED = "reviewed"  # System moved to reviewed, landlord can now approve/reject
    APPROVED = "approved"  # Landlord approved the application
    REJECTED = "rejected"  # Landlord rejected the application
    NEEDS_INFO = "needs_info"  # Landlord requested more information
    WITHDRAWN = "withdrawn"  # Tenant or system withdrew the application
    SIGNED = "signed"  # Contract agreed but move-in hasn't happened yet
    ACTIVE_LEASE = "active_lease"  # Move-in confirmed, lease is now live
    CLOSED = "closed"  # Lease terminated/completed

class Application(Base):
    """Application model"""
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)

    # Status
    status = Column(Enum(ApplicationStatus, native_enum=False), default=ApplicationStatus.DRAFT, nullable=False)

    # Application details
    message = Column(Text, nullable=True)
    move_in_date = Column(DateTime(timezone=True), nullable=True)
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
    documents_urls = Column(JSON, nullable=False, default=list)
    
    # References and consent
    references = Column(JSON, nullable=True)  # Array of references (name, phone, email, relationship)
    background_check_consent = Column(Boolean, default=False, nullable=False)

    # Metadata
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    
    # Lease tracking
    lease_signed_at = Column(DateTime(timezone=True), nullable=True, index=True)  # Timestamp when lease was signed

    # Foreign keys
    applicant_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False, index=True)

    # Relationships
    applicant = relationship("User", back_populates="applications")
    property = relationship("Property", back_populates="applications")

    # Constraints
    __table_args__ = (
        CheckConstraint('annual_income >= 0', name='chk_annual_income_nonnegative'),
        CheckConstraint('credit_score >= 0 AND credit_score <= 850', name='chk_credit_score_range'),
    )

    def __repr__(self):
        return f"<Application(id={self.id}, status='{self.status}', property_id={self.property_id})>"

