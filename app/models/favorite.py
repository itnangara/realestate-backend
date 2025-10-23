"""
Favorite model for user property favorites
"""

from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base

class Favorite(Base):
    """Favorite model"""
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Foreign keys
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="favorites")
    property = relationship("Property", back_populates="favorites")
    
    # Ensure unique user-property combination
    __table_args__ = (
        UniqueConstraint('user_id', 'property_id', name='unique_user_property_favorite'),
    )

    def __repr__(self):
        return f"<Favorite(id={self.id}, user_id={self.user_id}, property_id={self.property_id})>"


