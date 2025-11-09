"""
RefreshToken model for secure token management
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta, timezone
from app.utils.database import Base
from decouple import config

# Refresh token expiration (default 30 days)
REFRESH_TOKEN_EXPIRE_DAYS = int(config("REFRESH_TOKEN_EXPIRE_DAYS", default="30"))


class RefreshToken(Base):
    """Refresh token model for secure token rotation and revocation"""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(255), unique=True, nullable=False, index=True)  # Hashed token
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked = Column(Boolean, default=False, nullable=False, index=True)
    replaced_by = Column(String(255), nullable=True)  # Token ID that replaced this one (for rotation tracking)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Optional: Track device info for security auditing
    device_info = Column(String(255), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="refresh_tokens")

    # Composite index for fast queries
    __table_args__ = (
        Index("idx_user_revoked", "user_id", "revoked"),
        Index("idx_expires_revoked", "expires_at", "revoked"),
    )

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.revoked})>"
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired"""
        now = datetime.now(timezone.utc) if self.expires_at.tzinfo else datetime.utcnow()
        return now >= self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not revoked and not expired)"""
        return not self.revoked and not self.is_expired

