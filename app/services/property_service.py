"""
Property service for business logic
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from app.models.property import Property, PropertyType, PropertyStatus
from app.schemas.property import PropertyCreate, PropertyUpdate

class PropertyService:
    """Property service class"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_property_by_id(self, property_id: int) -> Optional[Property]:
        """Get property by ID"""
        return self.db.query(Property).filter(Property.id == property_id).first()
    
    def get_properties(
        self,
        skip: int = 0,
        limit: int = 20,
        city: Optional[str] = None,
        property_type: Optional[str] = None,
        status: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None
    ) -> List[Property]:
        """Get properties with filters"""
        query = self.db.query(Property).filter(Property.is_active == True)
        
        # Apply filters
        if city:
            query = query.filter(Property.city.ilike(f"%{city}%"))
        
        if property_type:
            query = query.filter(Property.property_type == property_type)
        
        if status:
            query = query.filter(Property.status == status)
        
        if min_price is not None:
            query = query.filter(Property.price >= min_price)
        
        if max_price is not None:
            query = query.filter(Property.price <= max_price)
        
        return query.offset(skip).limit(limit).all()
    
    def create_property(self, property_data: PropertyCreate, owner_id: int) -> Property:
        """Create a new property"""
        # Calculate price per sqft if both price and square_feet are provided
        price_per_sqft = None
        if property_data.price and property_data.square_feet:
            price_per_sqft = property_data.price / property_data.square_feet
        
        # Build features array from features field (if provided)
        features = property_data.features if hasattr(property_data, 'features') and property_data.features else []
        
        # Create property object
        property = Property(
            title=property_data.title,
            description=property_data.description,
            property_type=property_data.property_type,
            status=property_data.status,
            address=property_data.address,
            city=property_data.city,
            state=property_data.state,
            zip_code=property_data.zip_code,
            country=property_data.country,
            latitude=property_data.latitude,
            longitude=property_data.longitude,
            bedrooms=property_data.bedrooms,
            bathrooms=property_data.bathrooms,
            square_feet=property_data.square_feet,
            lot_size=property_data.lot_size,
            year_built=property_data.year_built,
            price=property_data.price,
            rent_price=property_data.rent_price,
            price_per_sqft=price_per_sqft,
            features=features if features else None,
            is_furnished=property_data.is_furnished,
            pet_friendly=property_data.pet_friendly,
            owner_id=owner_id
        )
        
        # Add to database
        self.db.add(property)
        self.db.commit()
        self.db.refresh(property)
        
        return property
    
    def update_property(self, property_id: int, property_data: PropertyUpdate) -> Optional[Property]:
        """Update a property"""
        property = self.get_property_by_id(property_id)
        if not property:
            return None
        
        # Update only actual database columns
        update_data = property_data.model_dump(exclude_unset=True)
        
        # Update remaining fields
        for field, value in update_data.items():
            setattr(property, field, value)
        
        # Recalculate price per sqft if price or square_feet changed
        if 'price' in update_data or 'square_feet' in update_data:
            if property.price and property.square_feet:
                property.price_per_sqft = property.price / property.square_feet
            else:
                property.price_per_sqft = None
        
        self.db.commit()
        self.db.refresh(property)
        
        return property
    
    def delete_property(self, property_id: int) -> bool:
        """Soft delete a property"""
        property = self.get_property_by_id(property_id)
        if not property:
            return False
        
        property.is_active = False
        self.db.commit()
        return True
    
    def get_user_properties(self, user_id: int) -> List[Property]:
        """Get properties owned by a user"""
        return self.db.query(Property).filter(
            and_(Property.owner_id == user_id, Property.is_active == True)
        ).all()
    
    def search_properties(self, search_filters: dict) -> List[Property]:
        """Search properties with advanced filters"""
        query = self.db.query(Property).filter(Property.is_active == True)
        
        # Apply all filters
        if search_filters.get('city'):
            query = query.filter(Property.city.ilike(f"%{search_filters['city']}%"))
        
        if search_filters.get('state'):
            query = query.filter(Property.state.ilike(f"%{search_filters['state']}%"))
        
        if search_filters.get('property_type'):
            query = query.filter(Property.property_type == search_filters['property_type'])
        
        if search_filters.get('status'):
            query = query.filter(Property.status == search_filters['status'])
        
        if search_filters.get('min_price'):
            query = query.filter(Property.price >= search_filters['min_price'])
        
        if search_filters.get('max_price'):
            query = query.filter(Property.price <= search_filters['max_price'])
        
        if search_filters.get('min_bedrooms'):
            query = query.filter(Property.bedrooms >= search_filters['min_bedrooms'])
        
        if search_filters.get('max_bedrooms'):
            query = query.filter(Property.bedrooms <= search_filters['max_bedrooms'])
        
        if search_filters.get('min_bathrooms'):
            query = query.filter(Property.bathrooms >= search_filters['min_bathrooms'])
        
        if search_filters.get('max_bathrooms'):
            query = query.filter(Property.bathrooms <= search_filters['max_bathrooms'])
        
        if search_filters.get('min_square_feet'):
            query = query.filter(Property.square_feet >= search_filters['min_square_feet'])
        
        if search_filters.get('max_square_feet'):
            query = query.filter(Property.square_feet <= search_filters['max_square_feet'])
        
        # Filter by features in JSON field
        if search_filters.get('has_garage') is not None:
            if search_filters['has_garage']:
                query = query.filter(Property.features.contains(['garage']))
            else:
                query = query.filter(~Property.features.contains(['garage']))
        
        if search_filters.get('has_pool') is not None:
            if search_filters['has_pool']:
                query = query.filter(Property.features.contains(['pool']))
            else:
                query = query.filter(~Property.features.contains(['pool']))
        
        if search_filters.get('pet_friendly') is not None:
            query = query.filter(Property.pet_friendly == search_filters['pet_friendly'])
        
        # Pagination
        skip = (search_filters.get('page', 1) - 1) * search_filters.get('limit', 20)
        limit = search_filters.get('limit', 20)
        
        return query.offset(skip).limit(limit).all()


