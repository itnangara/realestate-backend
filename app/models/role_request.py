"""
Role Request model for multi-role onboarding workflow
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Enum as SQLEnum
from app.utils.database import Base
from app.utils.types import ArrayType, JSONBType
import enum


class RoleRequestStatus(str, enum.Enum):
    """Role request status enum"""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class RoleRequest(Base):
    """
    Role Request model for tracking user requests for elevated roles
    
    Tracks the workflow: pending → in_review → approved/rejected
    """
    __tablename__ = "role_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Requested roles as array (e.g., ['seller', 'agent'])
    # Uses ArrayType for database-agnostic support (PostgreSQL ARRAY, SQLite JSON)
    requested_roles = Column(ArrayType(String), nullable=False)
    
    # Status tracking
    status = Column(
        SQLEnum(RoleRequestStatus, native_enum=True, values_callable=lambda obj: [e.value for e in obj]),
        default=RoleRequestStatus.PENDING,
        nullable=False,
        index=True
    )
    
    # Timestamps
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Review information
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    
    # Attachments and metadata
    # Uses JSONBType for database-agnostic support (PostgreSQL JSONB, SQLite JSON)
    attachments = Column(JSONBType, nullable=True)  # Array of document IDs
    trust_score = Column(Float, default=0.0, nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="role_requests")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    
    # Indexes for common queries
    __table_args__ = (
        Index("idx_role_requests_user_status", "user_id", "status"),
        Index("idx_role_requests_status_requested_at", "status", "requested_at"),
    )

    def __repr__(self):
        return f"<RoleRequest(id={self.id}, user_id={self.user_id}, status='{self.status.value}', requested_roles={self.requested_roles})>"

