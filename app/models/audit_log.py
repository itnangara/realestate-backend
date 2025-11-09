"""
Audit Log model for immutable audit trail
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base
from app.utils.types import JSONBType


class AuditLog(Base):
    """
    Audit Log model for immutable audit trail
    
    Records all actions with actor tracking (user, admin, or system)
    and structured JSON metadata for compliance and debugging.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Actor tracking - can be user_id, admin_id, or NULL for system actions
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Action details
    action = Column(String(255), nullable=False, index=True)  # e.g., "role_request_created", "role_granted"
    target_type = Column(String(50), nullable=True, index=True)  # e.g., "role_request", "kyc_request", "user"
    target_id = Column(Integer, nullable=True, index=True)  # ID of the target entity
    
    # Structured metadata (JSONB for querying)
    # Uses JSONBType for database-agnostic support (PostgreSQL JSONB, SQLite JSON)
    meta = Column(JSONBType, nullable=True)  # Additional context, request details, etc.
    
    # Request correlation
    request_id = Column(String(255), nullable=True, index=True)  # For correlating with HTTP request IDs
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Relationships
    actor = relationship("User", foreign_keys=[actor_id])
    
    # Indexes for common queries
    __table_args__ = (
        Index("idx_audit_logs_actor_action", "actor_id", "action"),
        Index("idx_audit_logs_target", "target_type", "target_id"),
        Index("idx_audit_logs_request_id", "request_id"),
        Index("idx_audit_logs_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<AuditLog(id={self.id}, actor_id={self.actor_id}, action='{self.action}', target_type='{self.target_type}', target_id={self.target_id})>"

