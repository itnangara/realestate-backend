"""
Property Serialization Utilities

Enterprise-grade helpers for serializing Property models to PropertyResponse schemas
with computed fields like is_owner.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.property import Property
from app.models.user import User
from app.schemas.property import PropertyResponse
from app.utils.property_ownership import is_property_owner


def serialize_property(property: Property, user: Optional[User], db: Session) -> PropertyResponse:
    """
    Serialize a Property model to PropertyResponse with computed is_owner field.
    
    Args:
        property: Property model instance
        user: Current authenticated user (None for public/guest)
        db: Database session for ownership checks
        
    Returns:
        PropertyResponse with is_owner computed
    """
    # Compute is_owner using unified ownership model
    is_owner = False
    if user:
        is_owner = is_property_owner(db, user.id, property.id)
    
    # Convert property to dict and add is_owner
    property_dict = {
        **property.__dict__,
        'is_owner': is_owner
    }
    
    # Remove SQLAlchemy internal attributes
    property_dict.pop('_sa_instance_state', None)
    
    return PropertyResponse.model_validate(property_dict)


def serialize_properties(properties: List[Property], user: Optional[User], db: Session) -> List[PropertyResponse]:
    """
    Serialize a list of Property models to PropertyResponse with computed is_owner fields.
    
    Args:
        properties: List of Property model instances
        user: Current authenticated user (None for public/guest)
        db: Database session for ownership checks
        
    Returns:
        List of PropertyResponse with is_owner computed
    """
    return [serialize_property(p, user, db) for p in properties]




