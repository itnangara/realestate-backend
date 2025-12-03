"""
UserProperty model for linking users to properties
Enterprise-grade unified model for all user-property relationships
"""

from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint, Index, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base
import enum


class RelationshipType(str, enum.Enum):
    """Relationship type enum for user-property associations"""
    BUYER = "BUYER"
    SELLER = "SELLER"
    AGENT = "AGENT"
    LANDLORD = "LANDLORD"
    TENANT = "TENANT"
    INVESTOR = "INVESTOR"
    ADMIN = "ADMIN"
    MAINTENANCE_STAFF = "MAINTENANCE_STAFF"


class UserProperty(Base):
    """
    UserProperty association model - Unified source of truth for all user-property relationships.
    
    Enterprise-grade: Single table for all relationship types (owner, tenant, maintenance, agent, etc.)
    This eliminates the need for Property.owner_id and provides consistent querying.
    """
    __tablename__ = "user_properties"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type = Column(
        Enum(RelationshipType, native_enum=True, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        index=True
    )
    
    # Audit trail
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="user_properties")
    property = relationship("Property", back_populates="user_properties")

    # Ensure unique user-property-relationship_type combination
    __table_args__ = (
        UniqueConstraint("user_id", "property_id", "relationship_type", name="uq_user_property_rel"),
        Index("ix_user_properties_user_id", "user_id"),
        Index("ix_user_properties_property_id", "property_id"),
        Index("ix_user_properties_relationship_type", "relationship_type"),
    )

    def __repr__(self):
        return f"<UserProperty(user_id={self.user_id}, property_id={self.property_id}, type={self.relationship_type.value})>"

