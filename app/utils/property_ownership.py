"""
Property Ownership Utilities

Enterprise-grade helper functions for checking property ownership and relationships.
Unified interface that uses user_properties table exclusively (no owner_id fallback).
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.user_property import UserProperty, RelationshipType
from app.models.property import Property
from app.core.logger import get_logger

logger = get_logger(__name__)


def is_property_owner(db: Session, user_id: int, property_id: int) -> bool:
    """
    Check if user is the owner of a property.
    
    Uses unified user_properties table exclusively.
    
    Args:
        db: Database session
        user_id: User ID to check
        property_id: Property ID to check
        
    Returns:
        True if user is owner, False otherwise
    """
    # Check user_properties with LANDLORD relationship
    landlord_link = (
        db.query(UserProperty)
        .filter(
            UserProperty.user_id == user_id,
            UserProperty.property_id == property_id,
            UserProperty.relationship_type == RelationshipType.LANDLORD
        )
        .first()
    )
    
    return landlord_link is not None


def has_property_access(
    db: Session,
    user_id: int,
    property_id: int,
    relationship_types: Optional[List[RelationshipType]] = None
) -> bool:
    """
    Check if user has any relationship to a property.
    
    Args:
        db: Database session
        user_id: User ID to check
        property_id: Property ID to check
        relationship_types: Optional list of relationship types to check.
                          If None, checks all types.
        
    Returns:
        True if user has any relationship, False otherwise
    """
    query = (
        db.query(UserProperty)
        .filter(
            UserProperty.user_id == user_id,
            UserProperty.property_id == property_id
        )
    )
    
    if relationship_types:
        query = query.filter(UserProperty.relationship_type.in_(relationship_types))
    
    link = query.first()
    
    return link is not None


def get_property_owners(db: Session, property_id: int) -> List[int]:
    """
    Get all owner user IDs for a property.
    
    Args:
        db: Database session
        property_id: Property ID
        
    Returns:
        List of user IDs who own the property
    """
    # Primary: Get from user_properties
    owner_links = (
        db.query(UserProperty)
        .filter(
            UserProperty.property_id == property_id,
            UserProperty.relationship_type == RelationshipType.LANDLORD
        )
        .all()
    )
    
    owner_ids = [link.user_id for link in owner_links]
    
    return owner_ids

