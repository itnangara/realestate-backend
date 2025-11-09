"""
KYC Request model for Know Your Customer verification workflow
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Enum as SQLEnum
from app.utils.database import Base
import enum


class KYCRequestStatus(str, enum.Enum):
    """KYC request status enum"""
    NOT_STARTED = "not_started"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"


class KYCRequest(Base):
    """
    KYC Request model for tracking KYC provider integration and verification status
    
    Links to role_requests and tracks provider responses for idempotency
    """
    __tablename__ = "kyc_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Provider integration - UNIQUE for idempotency
    provider_reference = Column(String(255), unique=True, nullable=True, index=True)
    
    # Status tracking
    status = Column(
        SQLEnum(KYCRequestStatus, native_enum=True, values_callable=lambda obj: [e.value for e in obj]),
        default=KYCRequestStatus.NOT_STARTED,
        nullable=False,
        index=True
    )
    
    # Provider response data
    verdict = Column(JSONB, nullable=True)  # Provider verdict payload
    raw_response = Column(JSONB, nullable=True)  # Full provider response for search/indexing
    
    # Timestamps
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Retry tracking
    attempts = Column(Integer, default=0, nullable=False)
    
    # Relationships
    user = relationship("User", backref="kyc_requests")
    
    # Indexes for common queries
    __table_args__ = (
        Index("idx_kyc_requests_user_status", "user_id", "status"),
        Index("idx_kyc_requests_provider_ref", "provider_reference"),
    )

    def __repr__(self):
        return f"<KYCRequest(id={self.id}, user_id={self.user_id}, status='{self.status.value}', provider_reference='{self.provider_reference}')>"

