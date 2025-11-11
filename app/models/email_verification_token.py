"""
Email Verification Token model for secure email verification
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.utils.database import Base


class EmailVerificationToken(Base):
    """
    Email verification token model for secure one-time email verification.
    
    Features:
    - One-time use tokens (used flag)
    - Token expiration (24 hours default)
    - Cascade delete when user is deleted
    - Indexed for fast lookups
    """
    __tablename__ = "email_verification_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationship
    user = relationship("User", back_populates="email_verification_tokens")

    # Composite indexes for efficient queries
    __table_args__ = (
        Index("idx_token_used", "token", "used"),
        Index("idx_user_unused", "user_id", "used"),
        Index("idx_expires_used", "expires_at", "used"),
    )

    def __repr__(self):
        return f"<EmailVerificationToken(id={self.id}, user_id={self.user_id}, used={self.used})>"
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired"""
        return datetime.now(timezone.utc) > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not used and not expired)"""
        return not self.used and not self.is_expired

