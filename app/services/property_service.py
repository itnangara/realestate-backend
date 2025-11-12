"""
Property service for business logic - Enterprise-grade role-aware CRUD
"""

import enum
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Optional, Tuple
from app.models.property import Property, PropertyType, PropertyStatus, ListingType
from app.models.user import User
from app.schemas.property import PropertyCreate, PropertyUpdate, PropertySearchFilters
from app.services.property_permissions import PropertyPermissionService, PUBLIC_LISTING_TYPES
from app.core.logger import get_logger

logger = get_logger(__name__)

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
        listing_type: Optional[str] = None,
        status: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None
    ) -> List[Property]:
        """Get properties with filters"""
        # Enterprise-grade: Filter out deleted properties by default
        query = self.db.query(Property).filter(
            Property.is_active == True,
            Property.status != PropertyStatus.DELETED
        )
        
        # Apply filters
        if city:
            query = query.filter(Property.city.ilike(f"%{city}%"))
        
        if property_type:
            query = query.filter(Property.property_type == property_type)
        
        if listing_type:
            query = query.filter(Property.listing_type == listing_type)
        
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
            listing_type=property_data.listing_type,
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
        # Enterprise-grade: Handle enum instances explicitly to ensure SQLAlchemy uses enum values
        for field, value in update_data.items():
            # Convert enum instances to their values for SQLAlchemy compatibility
            # This ensures values_callable works correctly with native_enum=True
            if hasattr(value, 'value') and isinstance(value, enum.Enum):
                setattr(property, field, value.value)
            else:
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
        """Soft delete a property - Enterprise-grade: uses status=DELETED"""
        property = self.get_property_by_id(property_id)
        if not property:
            return False
        
        # Enterprise-grade soft delete: set status to DELETED
        property.status = PropertyStatus.DELETED
        property.is_active = False  # Also set for consistency
        self.db.commit()
        return True
    
    def get_user_properties(self, user_id: int) -> List[Property]:
        """
        Get properties owned by a user.
        
        Enterprise-grade: Returns all properties owned by user (any status except DELETED).
        Role-based filtering is applied at the route layer using PropertyPermissionService.
        """
        return self.db.query(Property).filter(
            and_(
                Property.owner_id == user_id,
                Property.status != PropertyStatus.DELETED  # Exclude soft-deleted
            )
        ).all()
    
    def search_properties(self, search_filters: dict) -> List[Property]:
        """Search properties with advanced filters"""
        # Enterprise-grade: Filter out deleted properties by default
        query = self.db.query(Property).filter(
            Property.is_active == True,
            Property.status != PropertyStatus.DELETED
        )
        
        # Apply all filters
        if search_filters.get('city'):
            query = query.filter(Property.city.ilike(f"%{search_filters['city']}%"))
        
        if search_filters.get('state'):
            query = query.filter(Property.state.ilike(f"%{search_filters['state']}%"))
        
        if search_filters.get('property_type'):
            query = query.filter(Property.property_type == search_filters['property_type'])
        
        if search_filters.get('listing_type'):
            query = query.filter(Property.listing_type == search_filters['listing_type'])
        
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
    
    # --- Production-Grade Advanced Search Method ---
    
    # Whitelist allowed fields for sorting to prevent SQL injection
    SORTABLE_FIELDS = {
        "price": Property.price,
        "created_at": Property.created_at,
        "bedrooms": Property.bedrooms,
        "bathrooms": Property.bathrooms,
        "square_feet": Property.square_feet,
        "year_built": Property.year_built
    }
    
    def search_properties_advanced(self, filters: PropertySearchFilters) -> Tuple[List[Property], int]:
        """
        Advanced property search with type-safe sorting and filtering.
        Returns: (properties, total_count)
        """
        # Enterprise-grade: Filter out deleted properties by default
        query = self.db.query(Property).filter(
            Property.is_active == True,
            Property.status != PropertyStatus.DELETED
        )
        
        # --- Price Filters ---
        if filters.price_min is not None:
            query = query.filter(Property.price >= filters.price_min)
        if filters.price_max is not None:
            query = query.filter(Property.price <= filters.price_max)
        
        # --- Property Details ---
        if filters.property_type is not None:
            query = query.filter(Property.property_type == filters.property_type)
        
        # Handle listing_type filtering (singular for backward compatibility, plural for multiple values)
        if filters.listing_types is not None and len(filters.listing_types) > 0:
            # Multiple listing types - use IN clause for OR logic
            query = query.filter(Property.listing_type.in_(filters.listing_types))
        elif filters.listing_type is not None:
            # Single listing type - backward compatibility
            query = query.filter(Property.listing_type == filters.listing_type)
        if filters.bedrooms is not None:
            query = query.filter(Property.bedrooms >= filters.bedrooms)
        if filters.bathrooms is not None:
            query = query.filter(Property.bathrooms >= filters.bathrooms)
        if filters.square_feet_min is not None:
            query = query.filter(Property.square_feet >= filters.square_feet_min)
        if filters.square_feet_max is not None:
            query = query.filter(Property.square_feet <= filters.square_feet_max)
        
        # --- Location Filters ---
        if filters.city:
            query = query.filter(func.lower(Property.city) == filters.city.lower())
        if filters.state:
            query = query.filter(func.lower(Property.state) == filters.state.lower())
        if filters.zip_code:
            query = query.filter(Property.zip_code == filters.zip_code)
        if filters.country:
            query = query.filter(func.lower(Property.country) == filters.country.lower())
        
        # --- Features Filter (JSONB) ---
        if filters.features:
            feature_list = [f.strip() for f in filters.features.split(",") if f.strip()]
            conditions = [Property.features.contains([feature]) for feature in feature_list]
            query = query.filter(Property.features.isnot(None), or_(*conditions))
        
        # --- Status & Metadata ---
        if filters.status is not None:
            query = query.filter(Property.status == filters.status)
        if filters.is_featured is not None:
            query = query.filter(Property.is_featured == filters.is_featured)
        if filters.year_built_min is not None:
            query = query.filter(Property.year_built >= filters.year_built_min)
        if filters.year_built_max is not None:
            query = query.filter(Property.year_built <= filters.year_built_max)
        
        # --- Total Count Before Pagination ---
        total_count = query.count()
        
        # --- Secure Sorting ---
        sort_attr = self.SORTABLE_FIELDS.get(filters.sort_by, Property.created_at)
        if filters.sort_order == "desc":
            query = query.order_by(sort_attr.desc())
        else:
            query = query.order_by(sort_attr.asc())
        
        # --- Pagination ---
        offset = (filters.page - 1) * filters.limit
        properties = query.offset(offset).limit(filters.limit).all()
        
        return properties, total_count
    
    # ==================== Enterprise-Grade Role-Aware Methods ====================
    
    def get_properties_for_role(
        self,
        user: Optional[User],
        filters: PropertySearchFilters,
        skip: int = 0,
        limit: int = 20,
        role_context: Optional[str] = None
    ) -> Tuple[List[Property], int]:
        """
        Enterprise-grade role-aware property listing with role-context support.
        
        Rules:
        - Public/Guest: Only ACTIVE + public listing types (FOR_SALE, FOR_RENT, FOR_LEASE)
        - Buyer/Tenant: Same as public
        - Owner roles (Seller/Agent/Landlord/Investor): "My Listings" mode
          * If role_context provided: Only own properties matching that role's listing types
          * If role_context is None: Own properties matching any of user's owner roles (backward compatible)
        - Admin: All properties (any status, excluding DELETED - use get_all_properties_admin() to see deleted)
        
        Args:
            user: The user (None for public/guest)
            filters: Search filters
            skip: Pagination offset
            limit: Pagination limit
            role_context: Optional role context (seller, agent, landlord, investor)
                         For role-context-aware dashboards. Must be one of user's roles.
            
        Returns:
            Tuple of (properties list, total count)
        """
        query = self.db.query(Property)
        
        # Role-based visibility filtering
        if not user:
            # Public/Guest: Enterprise-grade granular filtering
            # BOTH conditions must be satisfied simultaneously:
            # 1. status = ACTIVE (property is publicly listed)
            # 2. listing_type IN [FOR_SALE, FOR_RENT, FOR_LEASE] (only public-facing types)
            # FOR_PORTFOLIO is explicitly excluded - never visible to public
            query = query.filter(
                Property.status == PropertyStatus.ACTIVE,
                Property.is_active == True,
                Property.listing_type.in_([lt.value for lt in PUBLIC_LISTING_TYPES])  # Explicitly excludes FOR_PORTFOLIO
            )
        elif user.has_role("admin"):
            # Admin: All properties except DELETED (use /all endpoint to see deleted)
            query = query.filter(Property.status != PropertyStatus.DELETED)
        elif user.has_role("buyer") or user.has_role("tenant"):
            # Buyer/Tenant: Enterprise-grade granular filtering
            # BOTH conditions must be satisfied simultaneously:
            # 1. status = ACTIVE (property is publicly listed)
            # 2. listing_type IN [FOR_SALE, FOR_RENT, FOR_LEASE] (only public-facing types)
            # FOR_PORTFOLIO is explicitly excluded - never visible to buyer/tenant
            query = query.filter(
                Property.status == PropertyStatus.ACTIVE,
                Property.is_active == True,
                Property.listing_type.in_([lt.value for lt in PUBLIC_LISTING_TYPES])  # Explicitly excludes FOR_PORTFOLIO
            )
        else:
            # Owner roles: "My Listings" mode - ONLY own properties with role-specific listing types
            owner_roles = ["seller", "agent", "landlord", "investor"]
            if any(user.has_role(role) for role in owner_roles):
                # Enterprise-grade: Authenticated owners see ONLY their own properties
                # with role-context-aware listing type filtering
                from app.services.property_permissions import PropertyPermissionService
                
                # Get role-context-aware listing types
                # If role_context provided, filters by that specific role only
                # If None, returns union of all user's owner roles (backward compatible)
                allowed_listing_types = PropertyPermissionService.get_owner_listing_types(
                    user, 
                    role_context=role_context
                )
                
                if allowed_listing_types:
                    query = query.filter(
                        and_(
                            Property.owner_id == user.id,  # Only own properties
                            Property.status != PropertyStatus.DELETED,  # Exclude deleted
                            Property.listing_type.in_([lt.value for lt in allowed_listing_types])  # Role-context-aware types
                        )
                    )
                else:
                    # No allowed listing types for this role context - return empty
                    query = query.filter(Property.id == -1)  # Impossible condition
            else:
                # Fallback: Public only (same granular filtering as public/guest)
                # BOTH conditions: status = ACTIVE AND listing_type IN public types
                query = query.filter(
                    Property.status == PropertyStatus.ACTIVE,
                    Property.is_active == True,
                    Property.listing_type.in_([lt.value for lt in PUBLIC_LISTING_TYPES])  # Explicitly excludes FOR_PORTFOLIO
                )
        
        # Apply additional filters from PropertySearchFilters
        if filters.price_min is not None:
            query = query.filter(Property.price >= filters.price_min)
        if filters.price_max is not None:
            query = query.filter(Property.price <= filters.price_max)
        
        if filters.property_type is not None:
            query = query.filter(Property.property_type == filters.property_type)
        
        # Listing type filtering (already filtered by role above, but allow further refinement)
        if filters.listing_types is not None and len(filters.listing_types) > 0:
            query = query.filter(Property.listing_type.in_([lt.value for lt in filters.listing_types]))
        elif filters.listing_type is not None:
            query = query.filter(Property.listing_type == filters.listing_type.value)
        
        if filters.bedrooms is not None:
            query = query.filter(Property.bedrooms >= filters.bedrooms)
        if filters.bathrooms is not None:
            query = query.filter(Property.bathrooms >= filters.bathrooms)
        if filters.square_feet_min is not None:
            query = query.filter(Property.square_feet >= filters.square_feet_min)
        if filters.square_feet_max is not None:
            query = query.filter(Property.square_feet <= filters.square_feet_max)
        
        # Location filters
        if filters.city:
            query = query.filter(func.lower(Property.city) == filters.city.lower())
        if filters.state:
            query = query.filter(func.lower(Property.state) == filters.state.lower())
        if filters.zip_code:
            query = query.filter(Property.zip_code == filters.zip_code)
        if filters.country:
            query = query.filter(func.lower(Property.country) == filters.country.lower())
        
        # Features filter
        if filters.features:
            feature_list = [f.strip() for f in filters.features.split(",") if f.strip()]
            conditions = [Property.features.contains([feature]) for feature in feature_list]
            query = query.filter(Property.features.isnot(None), or_(*conditions))
        
        # Status filter (if not already filtered by role)
        if filters.status is not None:
            if not user or (user and not user.has_role("admin")):
                # Only allow ACTIVE status for non-admin
                if filters.status == PropertyStatus.ACTIVE:
                    query = query.filter(Property.status == filters.status)
            else:
                # Admin can filter by any status except DELETED (use /all endpoint for deleted)
                if filters.status != PropertyStatus.DELETED:
                    query = query.filter(Property.status == filters.status)
        
        if filters.is_featured is not None:
            query = query.filter(Property.is_featured == filters.is_featured)
        if filters.year_built_min is not None:
            query = query.filter(Property.year_built >= filters.year_built_min)
        if filters.year_built_max is not None:
            query = query.filter(Property.year_built <= filters.year_built_max)
        
        # Total count before pagination
        total_count = query.count()
        
        # Sorting
        sort_attr = self.SORTABLE_FIELDS.get(filters.sort_by, Property.created_at)
        if filters.sort_order == "desc":
            query = query.order_by(sort_attr.desc())
        else:
            query = query.order_by(sort_attr.asc())
        
        # Pagination
        properties = query.offset(skip).limit(limit).all()
        
        return properties, total_count
    
    def get_all_properties_admin(
        self,
        filters: PropertySearchFilters,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[Property], int]:
        """
        Admin-only: Get all properties including deleted.
        
        Args:
            filters: Search filters
            skip: Pagination offset
            limit: Pagination limit
            
        Returns:
            Tuple of (properties list, total count)
        """
        query = self.db.query(Property)
        
        # Apply all filters (admin can see everything)
        if filters.price_min is not None:
            query = query.filter(Property.price >= filters.price_min)
        if filters.price_max is not None:
            query = query.filter(Property.price <= filters.price_max)
        
        if filters.property_type is not None:
            query = query.filter(Property.property_type == filters.property_type)
        
        if filters.listing_types is not None and len(filters.listing_types) > 0:
            query = query.filter(Property.listing_type.in_([lt.value for lt in filters.listing_types]))
        elif filters.listing_type is not None:
            query = query.filter(Property.listing_type == filters.listing_type.value)
        
        if filters.bedrooms is not None:
            query = query.filter(Property.bedrooms >= filters.bedrooms)
        if filters.bathrooms is not None:
            query = query.filter(Property.bathrooms >= filters.bathrooms)
        if filters.square_feet_min is not None:
            query = query.filter(Property.square_feet >= filters.square_feet_min)
        if filters.square_feet_max is not None:
            query = query.filter(Property.square_feet <= filters.square_feet_max)
        
        if filters.city:
            query = query.filter(func.lower(Property.city) == filters.city.lower())
        if filters.state:
            query = query.filter(func.lower(Property.state) == filters.state.lower())
        if filters.zip_code:
            query = query.filter(Property.zip_code == filters.zip_code)
        if filters.country:
            query = query.filter(func.lower(Property.country) == filters.country.lower())
        
        if filters.features:
            feature_list = [f.strip() for f in filters.features.split(",") if f.strip()]
            conditions = [Property.features.contains([feature]) for feature in feature_list]
            query = query.filter(Property.features.isnot(None), or_(*conditions))
        
        if filters.status is not None:
            query = query.filter(Property.status == filters.status)
        if filters.is_featured is not None:
            query = query.filter(Property.is_featured == filters.is_featured)
        if filters.year_built_min is not None:
            query = query.filter(Property.year_built >= filters.year_built_min)
        if filters.year_built_max is not None:
            query = query.filter(Property.year_built <= filters.year_built_max)
        
        total_count = query.count()
        
        sort_attr = self.SORTABLE_FIELDS.get(filters.sort_by, Property.created_at)
        if filters.sort_order == "desc":
            query = query.order_by(sort_attr.desc())
        else:
            query = query.order_by(sort_attr.asc())
        
        properties = query.offset(skip).limit(limit).all()
        
        return properties, total_count
    
    def create_property_with_role_check(
        self,
        property_data: PropertyCreate,
        user: User,
        request_id: Optional[str] = None
    ) -> Property:
        """
        Enterprise-grade: Create property with role-based permission check.
        
        Args:
            property_data: Property creation data
            user: The user creating the property
            request_id: Request ID for audit logging
            
        Returns:
            Created property
            
        Raises:
            ValueError: If user doesn't have permission for the listing type
        """
        # Check listing type permission
        if property_data.listing_type:
            if not PropertyPermissionService.can_create_listing_type(user, property_data.listing_type):
                logger.warning(
                    event="property_creation_permission_denied",
                    request_id=request_id or "unknown",
                    user_id=user.id,
                    user_email=user.email,
                    listing_type=property_data.listing_type.value,
                    user_roles=user.roles
                )
                raise ValueError(
                    f"User role does not allow creating {property_data.listing_type.value} properties"
                )
        
        # Create property
        property = self.create_property(property_data, user.id)
        
        # Audit log
        logger.info(
            event="property_created",
            request_id=request_id or "unknown",
            user_id=user.id,
            user_email=user.email,
            property_id=property.id,
            property_title=property.title,
            listing_type=property.listing_type.value if property.listing_type else None,
            status=property.status.value,
            property_type=property.property_type.value
        )
        
        return property
    
    def update_property_with_role_check(
        self,
        property_id: int,
        property_data: PropertyUpdate,
        user: User,
        request_id: Optional[str] = None
    ) -> Property:
        """
        Enterprise-grade: Update property with role-based permission check.
        
        Args:
            property_id: ID of property to update
            property_data: Property update data
            user: The user updating the property
            request_id: Request ID for audit logging
            
        Returns:
            Updated property
            
        Raises:
            ValueError: If user doesn't have permission to update
        """
        property = self.get_property_by_id(property_id)
        if not property:
            raise ValueError("Property not found")
        
        # Enterprise-grade: Explicit ownership check before update
        # Service layer always verifies ownership (property.owner_id == user.id) OR admin role
        # This prevents unauthorized updates even if route layer is bypassed
        if not PropertyPermissionService.can_update_property(user, property):
            logger.warning(
                event="property_update_permission_denied",
                request_id=request_id or "unknown",
                user_id=user.id,
                user_email=user.email,
                property_id=property_id,
                property_owner_id=property.owner_id,
                user_roles=user.roles
            )
            raise ValueError("User does not have permission to update this property")
        
        # Check listing type permission if changing listing_type
        if property_data.listing_type and property_data.listing_type != property.listing_type:
            if not PropertyPermissionService.can_create_listing_type(user, property_data.listing_type):
                raise ValueError(
                    f"User role does not allow creating {property_data.listing_type.value} properties"
                )
        
        # Track changes for audit
        old_status = property.status.value
        old_listing_type = property.listing_type.value if property.listing_type else None
        
        # Update property
        updated_property = self.update_property(property_id, property_data)
        
        # Audit log
        logger.info(
            event="property_updated",
            request_id=request_id or "unknown",
            user_id=user.id,
            user_email=user.email,
            property_id=property_id,
            old_status=old_status,
            new_status=updated_property.status.value,
            old_listing_type=old_listing_type,
            new_listing_type=updated_property.listing_type.value if updated_property.listing_type else None,
            changed_fields=list(property_data.model_dump(exclude_unset=True).keys())
        )
        
        return updated_property
    
    def delete_property_with_role_check(
        self,
        property_id: int,
        user: User,
        request_id: Optional[str] = None
    ) -> bool:
        """
        Enterprise-grade: Soft delete property with role-based permission check.
        
        Uses status=DELETED for soft delete as per enterprise requirements.
        
        Args:
            property_id: ID of property to delete
            user: The user deleting the property
            request_id: Request ID for audit logging
            
        Returns:
            True if deleted successfully
            
        Raises:
            ValueError: If user doesn't have permission to delete
        """
        property = self.get_property_by_id(property_id)
        if not property:
            raise ValueError("Property not found")
        
        # Enterprise-grade: Explicit ownership check before delete
        # Service layer always verifies ownership (property.owner_id == user.id) OR admin role
        # This prevents unauthorized deletes even if route layer is bypassed
        if not PropertyPermissionService.can_delete_property(user, property):
            logger.warning(
                event="property_delete_permission_denied",
                request_id=request_id or "unknown",
                user_id=user.id,
                user_email=user.email,
                property_id=property_id,
                property_owner_id=property.owner_id,
                user_roles=user.roles
            )
            raise ValueError("User does not have permission to delete this property")
        
        # Soft delete using status=DELETED
        property.status = PropertyStatus.DELETED
        property.is_active = False
        self.db.commit()
        self.db.refresh(property)
        
        # Audit log
        logger.info(
            event="property_deleted",
            request_id=request_id or "unknown",
            user_id=user.id,
            user_email=user.email,
            property_id=property_id,
            property_title=property.title,
            listing_type=property.listing_type.value if property.listing_type else None,
            deleted_by_role=user.roles
        )
        
        return True



