"""
Viewing models for property viewing requests and appointment booking.
"""

from datetime import datetime, timezone
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from app.utils.database import Base


class ViewingStatus(str, enum.Enum):
    """Viewing request lifecycle."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DECLINED = "DECLINED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class ViewingRequest(Base):
    """Property viewing request created by a prospective tenant or buyer."""

    __tablename__ = "viewing_requests"

    id = Column(Integer, primary_key=True, index=True)

    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    status = Column(Enum(ViewingStatus, native_enum=False), default=ViewingStatus.PENDING, nullable=False, index=True)
    requested_slots = Column(JSON, nullable=False, default=list)
    confirmed_slot = Column(DateTime(timezone=True), nullable=True, index=True)

    message = Column(Text, nullable=True)
    response_note = Column(Text, nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    responded_at = Column(DateTime(timezone=True), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)

    property = relationship("Property", backref="viewing_requests")
    requester = relationship("User", foreign_keys=[requester_id], backref="requested_viewings")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], backref="assigned_viewings")

    __table_args__ = (
        Index("ix_viewing_request_property_status", "property_id", "status"),
        Index("ix_viewing_request_requester_status", "requester_id", "status"),
        Index("ix_viewing_request_assigned_status", "assigned_to_id", "status"),
        Index("ix_viewing_request_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<ViewingRequest(id={self.id}, property_id={self.property_id}, status='{self.status}')>"
