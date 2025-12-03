"""
Test helpers for creating properties with unified ownership model.

Enterprise-grade: All property creation in tests uses user_properties table.
"""

from app.models.property import Property, PropertyType, PropertyStatus, ListingType
from app.models.user_property import UserProperty, RelationshipType
from sqlalchemy.orm import Session


def create_test_property(
    db: Session,
    owner_id: int,
    title: str = "Test Property",
    property_type: PropertyType = PropertyType.HOUSE,
    listing_type: ListingType = ListingType.FOR_SALE,
    status: PropertyStatus = PropertyStatus.ACTIVE,
    address: str = "123 Test St",
    city: str = "Test City",
    state: str = "TS",
    zip_code: str = "12345",
    country: str = "USA",
    price: float = 100000.0,
    rent_price: float = None,
    is_active: bool = True,
    **kwargs
) -> Property:
    """
    Create a test property with unified ownership model.
    
    Enterprise-grade: Creates property and user_properties link atomically.
    
    Args:
        db: Database session
        owner_id: User ID to assign as owner (creates LANDLORD relationship)
        **kwargs: Additional property fields
        
    Returns:
        Created Property instance
    """
    # Create property (no owner_id field)
    property = Property(
        title=title,
        property_type=property_type,
        listing_type=listing_type,
        status=status,
        address=address,
        city=city,
        state=state,
        zip_code=zip_code,
        country=country,
        price=price,
        rent_price=rent_price,
        is_active=is_active,
        **kwargs
    )
    
    db.add(property)
    db.flush()  # Get property ID
    
    # Create unified user_properties link
    if owner_id:
        link = UserProperty(
            user_id=owner_id,
            property_id=property.id,
            relationship_type=RelationshipType.LANDLORD
        )
        db.add(link)
    
    db.commit()
    db.refresh(property)
    
    return property




