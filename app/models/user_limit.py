"""
User Limit model for quota tracking
"""

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class UserLimit(Base):
    """
    User Limit model for tracking user quotas and limits
    
    Tracks per-user quota counters (e.g., listings_remaining_today)
    for rate limiting and feature gating.
    """
    __tablename__ = "user_limits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # Quota counters
    listings_remaining_today = Column(Integer, default=0, nullable=False)
    
    # Timestamps
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", backref="user_limit")
    
    # Ensure one limit record per user
    __table_args__ = (
        UniqueConstraint("user_id", name="unique_user_limit"),
    )

    def __repr__(self):
        return f"<UserLimit(id={self.id}, user_id={self.user_id}, listings_remaining_today={self.listings_remaining_today})>"

