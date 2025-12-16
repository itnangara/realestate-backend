"""
Maintenance models for property maintenance request management
Enterprise-grade models following industry-standard maintenance workflow
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, Numeric, Index, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON
from app.utils.database import Base
from datetime import datetime, timezone
import enum


class MaintenanceStatus(str, enum.Enum):
    """Maintenance status enum - enterprise-grade unified workflow"""
    REPORTED = "REPORTED"  # Tenant submits request
    
    # TODO: Rename "REVIEWING" to "IN_REVIEW"

    REVIEWING = "REVIEWING"  # Property Manager reviews
    ASSIGNED = "ASSIGNED"  # Manager assigns task
    ACKNOWLEDGED = "ACKNOWLEDGED"  # Staff acknowledges
    IN_PROGRESS = "IN_PROGRESS"  # Maintenance in progress
    COMPLETED = "COMPLETED"  # Staff marks done
    VERIFIED = "VERIFIED"  # Manager verifies completion
    CLOSED = "CLOSED"  # Tenant confirms satisfaction
    REJECTED = "REJECTED"  # Invalid request rejected
    CANCELLED = "CANCELLED"  # Request cancelled
    REOPENED = "REOPENED"  # Issue reopened after completion


class MaintenancePriority(str, enum.Enum):
    """Maintenance priority enum"""
    LOW = "LOW"  # Cosmetic issues
    MEDIUM = "MEDIUM"  # Normal priority
    HIGH = "HIGH"  # Time-sensitive
    EMERGENCY = "EMERGENCY"  # Health/safety critical


class MaintenanceCategory(str, enum.Enum):
    """Maintenance category enum"""
    PLUMBING = "PLUMBING"
    ELECTRICAL = "ELECTRICAL"
    HVAC = "HVAC"  # Heating/Cooling
    APPLIANCE = "APPLIANCE"
    STRUCTURAL = "STRUCTURAL"
    PEST_CONTROL = "PEST_CONTROL"
    CLEANING = "CLEANING"
    GENERAL = "GENERAL"
    OTHER = "OTHER"


class MaintenanceRequest(Base):
    """
    Maintenance request model - enterprise-grade maintenance tracking
    
    Workflow: REPORTED → REVIEWING → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS → COMPLETED → VERIFIED → CLOSED
    """
    __tablename__ = "maintenance_requests"

    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_number = Column(String(50), nullable=True)  # Unit number (for multi-unit properties)
    tenant_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reported_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # Who reported (usually tenant)
    assigned_staff_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Assigned maintenance staff
    
    # Request details
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(Enum(MaintenancePriority, native_enum=False), default=MaintenancePriority.MEDIUM, nullable=False, index=True)
    category = Column(Enum(MaintenanceCategory, native_enum=False), default=MaintenanceCategory.GENERAL, nullable=False)
    status = Column(Enum(MaintenanceStatus, native_enum=False), default=MaintenanceStatus.REPORTED, nullable=False, index=True)
    
    # Cost tracking
    estimated_cost = Column(Numeric(12, 2), nullable=True)
    actual_cost = Column(Numeric(12, 2), nullable=True)
    cost_approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Who approved the cost
    
    # External vendor (optional - for external contractors)
    external_vendor_name = Column(String(255), nullable=True)
    external_vendor_contact = Column(String(255), nullable=True)
    
    # Access and scheduling (industry-standard fields)
    access_instructions = Column(Text, nullable=True)  # Instructions for maintenance team entry
    preferred_date = Column(DateTime(timezone=True), nullable=True)  # Preferred date for maintenance visit
    preferred_time = Column(String(20), nullable=True)  # Preferred time: "Morning", "Afternoon", "Evening"
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    last_status_change = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    
    # Soft delete
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Relationships
    property = relationship("Property", backref="maintenance_requests")
    tenant = relationship("User", foreign_keys=[tenant_id], backref="tenant_maintenance_requests")
    reported_by = relationship("User", foreign_keys=[reported_by_id], backref="reported_maintenance_requests")
    assigned_staff = relationship("User", foreign_keys=[assigned_staff_id], backref="assigned_maintenance_requests")
    cost_approved_by = relationship("User", foreign_keys=[cost_approved_by_id])
    status_history = relationship("MaintenanceStatusHistory", back_populates="request", cascade="all, delete-orphan", order_by="MaintenanceStatusHistory.changed_at")
    attachments = relationship("MaintenanceAttachment", back_populates="request", cascade="all, delete-orphan")
    activities = relationship("MaintenanceActivity", back_populates="request", cascade="all, delete-orphan", order_by="MaintenanceActivity.created_at")
    
    # Indexes for performance
    __table_args__ = (
        Index("ix_maintenance_request_property_id", "property_id"),
        Index("ix_maintenance_request_status", "status"),
        Index("ix_maintenance_request_priority", "priority"),
        Index("ix_maintenance_request_tenant_id", "tenant_id"),
        Index("ix_maintenance_request_assigned_staff_id", "assigned_staff_id"),
        Index("ix_maintenance_request_created_at", "created_at"),
        Index("ix_maintenance_request_is_active", "is_active"),
    )

    def __repr__(self):
        return f"<MaintenanceRequest(id={self.id}, status='{self.status}', property_id={self.property_id})>"


class MaintenanceStatusHistory(Base):
    """
    Maintenance status history - audit trail for status changes
    Enterprise-grade: tracks all status transitions with actor and notes
    """
    __tablename__ = "maintenance_status_history"

    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    request_id = Column(Integer, ForeignKey("maintenance_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Status change details
    old_status = Column(String(30), nullable=True)  # Previous status
    new_status = Column(String(30), nullable=False)  # New status
    note = Column(Text, nullable=True)  # Optional note explaining the change
    
    # Timestamp
    changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    
    # Relationships
    request = relationship("MaintenanceRequest", back_populates="status_history")
    changed_by = relationship("User", backref="maintenance_status_changes")
    
    # Indexes
    __table_args__ = (
        Index("ix_maintenance_status_history_request_id", "request_id"),
        Index("ix_maintenance_status_history_changed_at", "changed_at"),
    )

    def __repr__(self):
        return f"<MaintenanceStatusHistory(id={self.id}, request_id={self.request_id}, {self.old_status}→{self.new_status})>"


class MaintenanceAttachment(Base):
    """
    Maintenance attachment model - stores file metadata
    Enterprise-grade: supports photos, videos, documents
    """
    __tablename__ = "maintenance_attachments"

    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    request_id = Column(Integer, ForeignKey("maintenance_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # File details
    file_url = Column(String(500), nullable=False)  # S3 URL or file path
    file_type = Column(String(50), nullable=True)  # image/jpeg, application/pdf, etc.
    file_name = Column(String(255), nullable=True)  # Original filename
    file_size = Column(Integer, nullable=True)  # File size in bytes
    
    # Metadata
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    description = Column(Text, nullable=True)  # Optional description
    
    # Relationships
    request = relationship("MaintenanceRequest", back_populates="attachments")
    uploaded_by = relationship("User", backref="maintenance_attachments")
    
    # Indexes
    __table_args__ = (
        Index("ix_maintenance_attachment_request_id", "request_id"),
        Index("ix_maintenance_attachment_uploaded_at", "uploaded_at"),
    )

    def __repr__(self):
        return f"<MaintenanceAttachment(id={self.id}, request_id={self.request_id}, file_url='{self.file_url[:50]}...')>"


class MaintenanceActivity(Base):
    """
    Maintenance activity model - timeline of events and actions
    Enterprise-grade: comprehensive activity log for audit and transparency
    """
    __tablename__ = "maintenance_activities"

    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    request_id = Column(Integer, ForeignKey("maintenance_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # Who performed the action
    
    # Activity details
    action_type = Column(String(50), nullable=False)  # status_change, assignment, comment, attachment, etc.
    action_data = Column(JSON, nullable=True)  # Flexible JSON for action-specific data
    description = Column(Text, nullable=True)  # Human-readable description
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    
    # Relationships
    request = relationship("MaintenanceRequest", back_populates="activities")
    actor = relationship("User", backref="maintenance_activities")
    
    # Indexes
    __table_args__ = (
        Index("ix_maintenance_activity_request_id", "request_id"),
        Index("ix_maintenance_activity_created_at", "created_at"),
        Index("ix_maintenance_activity_action_type", "action_type"),
    )

    def __repr__(self):
        return f"<MaintenanceActivity(id={self.id}, request_id={self.request_id}, action='{self.action_type}')>"

