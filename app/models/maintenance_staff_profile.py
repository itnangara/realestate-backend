"""
Maintenance Staff Profile model for users with maintenance_staff role
Enterprise-grade profile model following industry standards
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, ARRAY, Index, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class MaintenanceStaffProfile(Base):
    """
    Maintenance Staff Profile model
    
    Stores additional information for maintenance staff users.
    Enterprise-grade: supports skills tracking, contact info, and active status.
    """
    __tablename__ = "maintenance_staff_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # Professional Information
    skills = Column(ARRAY(String), nullable=True)  # Array of skills (e.g., ["plumbing", "electrical", "hvac"])
    phone_number = Column(String(20), nullable=True)  # Direct contact number for maintenance staff
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Audit trail
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    user = relationship("User", back_populates="maintenance_staff_profile")

    # Indexes for performance
    __table_args__ = (
        Index("ix_maintenance_staff_profile_user_id", "user_id"),
        Index("ix_maintenance_staff_profile_is_active", "is_active"),
    )

    def __repr__(self):
        return f"<MaintenanceStaffProfile(user_id={self.user_id}, is_active={self.is_active})>"

