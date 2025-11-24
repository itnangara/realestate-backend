"""
Lease model for rental lease management
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, Numeric, Index, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON
from app.utils.database import Base
from datetime import datetime, timezone
import enum


class LeaseStatus(str, enum.Enum):
    """Lease status enum - enterprise-grade unified workflow"""
    DRAFT = "draft"  # Lease draft created, not yet sent
    SENT = "sent"  # Lease sent to tenant for signing
    SIGNED = "signed"  # Tenant signed, awaiting landlord counter-signature
    COUNTER_SIGNED = "counter_signed"  # Both parties signed
    ACTIVE = "active"  # Lease is active (move-in confirmed)
    TERMINATED = "terminated"  # Lease ended/terminated
    CANCELLED = "cancelled"  # Lease cancelled (different from terminated)


class Lease(Base):
    """Lease model for rental agreements"""
    __tablename__ = "leases"

    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=True, index=True)  # Nullable for manual leases
    landlord_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False, index=True)
    
    # Financial terms
    rent = Column(Numeric(12, 2), nullable=False)  # Monthly rent
    deposit = Column(Numeric(12, 2), nullable=True)  # Security deposit
    
    # Lease dates
    start_date = Column(DateTime(timezone=True), nullable=True)  # Lease start date
    end_date = Column(DateTime(timezone=True), nullable=True)  # Lease end date
    
    # Terms and conditions
    terms = Column(Text, nullable=True)  # Lease terms (markdown or plain text)
    clauses = Column(JSON, nullable=True)  # Array of clauses (JSON for flexibility)
    
    # Status
    status = Column(Enum(LeaseStatus, native_enum=False), default=LeaseStatus.DRAFT, nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)  # When lease was sent to tenant
    signed_at = Column(DateTime(timezone=True), nullable=True)  # When lease was fully signed
    activated_at = Column(DateTime(timezone=True), nullable=True)  # When lease was activated
    
    # Relationships
    application = relationship("Application", backref="leases")
    landlord = relationship("User", foreign_keys=[landlord_id], backref="landlord_leases")
    tenant = relationship("User", foreign_keys=[tenant_id], backref="tenant_leases")
    property = relationship("Property", backref="leases")
    signatures = relationship("LeaseSignature", back_populates="lease", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        CheckConstraint('rent >= 0', name='chk_rent_nonnegative'),
        CheckConstraint('deposit >= 0', name='chk_deposit_nonnegative'),
        Index("ix_lease_application_id", "application_id"),
        Index("ix_lease_property_id", "property_id"),
        Index("ix_lease_status", "status"),
        Index("ix_lease_landlord_id", "landlord_id"),
        Index("ix_lease_tenant_id", "tenant_id"),
    )

    def __repr__(self):
        return f"<Lease(id={self.id}, status='{self.status}', property_id={self.property_id})>"


class LeaseSignature(Base):
    """Lease signature model for tracking who signed when"""
    __tablename__ = "lease_signatures"

    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    lease_id = Column(Integer, ForeignKey("leases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Signature details
    role = Column(String(50), nullable=False)  # 'tenant' or 'landlord'
    signature_text = Column(Text, nullable=True)  # Typed signature or e-signature data
    signed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    method = Column(String(50), nullable=False, default="manual")  # 'manual', 'esig', etc.
    
    # Metadata
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)  # Browser/client info
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    
    # Relationships
    lease = relationship("Lease", back_populates="signatures")
    user = relationship("User", backref="lease_signatures")
    
    # Constraints - ensure one signature per user per lease
    __table_args__ = (
        Index("ix_lease_signature_lease_user", "lease_id", "user_id", unique=True),
    )

    def __repr__(self):
        return f"<LeaseSignature(id={self.id}, lease_id={self.lease_id}, user_id={self.user_id}, role='{self.role}')>"

