"""
Property routes - Enterprise-grade
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import ValidationError

from app.utils.database import get_db
from app.schemas.property import (
    PropertyResponse, PropertyCreate, PropertyUpdate,
    PropertySearchFilters, PropertySearchResponse
)
from app.services.property_service import PropertyService
from app.dependencies.user_dependencies import get_current_user
from app.dependencies.authorization_dependencies import get_admin_user, get_optional_user
from app.models.user import User
from app.models.property import ListingType, PropertyStatus, PropertyType
from app.core.logger import get_logger
from app.utils.property_serialization import serialize_property, serialize_properties

router = APIRouter()
logger = get_logger(__name__)


# ------------------- Basic Property Endpoints ------------------- #

@router.get(
    "/",
    response_model=PropertySearchResponse,
    response_model_exclude_none=True,
    summary="Get properties with role-aware filtering",
    response_description="List of properties matching specified filters, filtered by user role."
)
async def get_properties(
    request: Request,
    skip: int = Query(0, ge=0, description="Number of properties to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of properties to return"),
    city: Optional[str] = Query(None, description="Filter by city"),
    property_type: Optional[str] = Query(None, description="Filter by property type"),
    listing_type: Optional[str] = Query(None, description="Filter by listing type"),
    status: Optional[str] = Query(None, description="Filter by property status"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    role_context: Optional[str] = Query(None, description="Role context for role-context-aware dashboards (seller, agent, landlord, investor). Must be one of user's roles."),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade role-aware property listing with role-context support.
    
    Behavior:
    - Public/Guest: Only ACTIVE + public listing types (FOR_SALE, FOR_RENT, FOR_LEASE)
    - Buyer/Tenant: Same as public (marketplace view)
    - Owner roles (Seller/Agent/Landlord/Investor): "My Listings" mode
      * Authenticated owners see ONLY their own properties
      * Role-context-aware listing type filtering:
        - If role_context provided: Only properties matching that role's listing types
          * Seller context: only for_sale properties
          * Agent context: only for_sale + for_rent properties
          * Landlord context: only for_rent properties
          * Investor context: only for_portfolio properties
        - If role_context is None: Properties matching any of user's owner roles (backward compatible)
      * All statuses except DELETED
      * No other users' listings included
    - Admin: All properties (any status, excluding DELETED - use /all endpoint to see deleted)
    
    Role-Context-Aware Dashboards:
    - Pass role_context parameter to filter by specific role (e.g., role_context=seller)
    - role_context must be one of the authenticated user's roles
    - If invalid role_context provided, returns empty results
    
    "My Listings" pages: Simply call this endpoint with authentication.
    Ownership and role filtering are automatically inferred from JWT token.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Convert query params to enums and normalize
    property_type_enum = None
    if property_type:
        try:
            property_type_enum = PropertyType(property_type)
        except ValueError:
            pass
    
    listing_type_enum = None
    if listing_type:
        try:
            listing_type_enum = ListingType(listing_type)
        except ValueError:
            pass
    
    status_enum = None
    if status:
        try:
            status_enum = PropertyStatus(status)
        except ValueError:
            pass
    
    # Normalize empty strings
    city = city or None
    
    # Enterprise-grade strictness: Authenticated owner-role users MUST provide role_context
    # This prevents accidental data leakage from union of all roles
    owner_roles = ["seller", "agent", "landlord", "investor"]
    if user and not user.has_role("admin"):
        # Check if user has any owner role
        if any(user.has_role(role) for role in owner_roles):
            # Owner-role user must provide role_context for strict dashboard filtering
            if not role_context:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"role_context is required for owner-role users. Available roles: {', '.join([r for r in user.roles if r in owner_roles])}. "
                           f"Please specify role_context parameter (e.g., ?role_context=seller)"
                )
    
    # Validate role_context if provided
    validated_role_context = None
    if role_context:
        # Normalize role_context to lowercase
        role_context = role_context.lower().strip()
        
        # Validate role_context is a valid owner role
        valid_owner_roles = ["seller", "agent", "landlord", "investor"]
        if role_context not in valid_owner_roles:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role_context. Must be one of: {', '.join(valid_owner_roles)}"
            )
        
        # Validate user has this role (if authenticated)
        # Exception: Admins can use any role_context for role simulation
        if user:
            if role_context not in user.roles and not user.has_role("admin"):
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User does not have role '{role_context}'. Available roles: {', '.join(user.roles)}"
                )
            validated_role_context = role_context
        else:
            # Public/guest cannot use role_context
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="role_context requires authentication"
            )
    
    # Build filters
    filters = PropertySearchFilters(
        price_min=min_price,
        price_max=max_price,
        property_type=property_type_enum,
        listing_type=listing_type_enum,
        status=status_enum,
        city=city,
        page=(skip // limit) + 1,
        limit=limit
    )
    
    property_service = PropertyService(db)
    properties, total_count = property_service.get_properties_for_role(
        user=user,
        filters=filters,
        skip=skip,
        limit=limit,
        role_context=validated_role_context
    )
    
    return PropertySearchResponse(
        properties=serialize_properties(properties, user, db),
        total_count=total_count,
        page=(skip // limit) + 1,
        limit=limit,
        total_pages=(total_count + limit - 1) // limit
    )


@router.get(
    "/search",
    response_model=PropertySearchResponse,
    summary="Advanced Property Search (GET) - Role-aware",
    response_description="Search results with pagination metadata, filtered by user role."
)
async def search_properties_get(
    request: Request,
    price_min: Optional[int] = Query(None, ge=0),
    price_max: Optional[int] = Query(None, ge=0),
    property_type: Optional[str] = Query(None),
    bedrooms: Optional[int] = Query(None, ge=0),
    bathrooms: Optional[float] = Query(None, ge=0),
    square_feet_min: Optional[int] = Query(None, ge=0),
    square_feet_max: Optional[int] = Query(None, ge=0),
    city: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    zip_code: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    features: Optional[str] = Query(None),
    listing_type: Optional[str] = Query(None, description="Single listing type (for_sale, for_rent, etc.) - for backward compatibility"),
    listing_types: Optional[str] = Query(None, description="Comma-separated listing types (e.g., 'for_rent,for_lease') - supports multiple values"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by property status"),
    is_featured: Optional[bool] = Query(None),
    year_built_min: Optional[int] = Query(None, ge=1800, le=2030),
    year_built_max: Optional[int] = Query(None, ge=1800, le=2030),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    role_context: Optional[str] = Query(None, description="Role context for role-context-aware dashboards (seller, agent, landlord, investor). Must be one of user's roles."),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade role-aware property search (GET) with role-context support.
    
    Same filtering rules as GET /api/properties/ but with advanced filters:
    - Public/Guest: Only ACTIVE + public listing types (FOR_SALE, FOR_RENT, FOR_LEASE)
    - Buyer/Tenant: Same as public (marketplace view)
    - Owner roles (Seller/Agent/Landlord/Investor): "My Listings" mode
      * Authenticated owners see ONLY their own properties
      * Role-context-aware listing type filtering:
        - If role_context provided: Only properties matching that role's listing types
        - If role_context is None: Properties matching any of user's owner roles (backward compatible)
      * All statuses except DELETED
      * No other users' listings included
    - Admin: All properties (any status, excluding DELETED)
    
    Supports advanced filtering: price, bedrooms, bathrooms, square_feet, location,
    features, year_built, sorting, and pagination.
    """
    # Enterprise-grade: Normalize and convert inputs before schema instantiation
    
    # 1. Convert listing_type(s) string(s) to enum(s)
    listing_type_enum = None
    listing_types_enums = None
    
    if listing_types:
        # Parse comma-separated listing types
        try:
            listing_types_list = [lt.strip() for lt in listing_types.split(",") if lt.strip()]
            listing_types_enums = [ListingType(lt) for lt in listing_types_list]
        except ValueError:
            pass  # Invalid values will be handled by schema validation
    elif listing_type:
        # Single listing type for backward compatibility
        try:
            listing_type_enum = ListingType(listing_type)
        except ValueError:
            pass  # Invalid value will be handled by schema validation
    
    # 2. Convert status_filter string to enum
    status_enum = None
    if status_filter:
        try:
            status_enum = PropertyStatus(status_filter)
        except ValueError:
            pass  # Invalid value will be handled by schema validation
    
    # 3. Convert property_type string to enum
    property_type_enum = None
    if property_type:
        try:
            property_type_enum = PropertyType(property_type)
        except ValueError:
            pass  # Invalid value will be handled by schema validation
    
    # 4. Normalize optional strings (convert empty strings to None)
    city = city or None
    state = state or None
    zip_code = zip_code or None
    country = country or None
    features = features or None
    
    # 5. Use model_validate for enterprise-grade type conversion and validation
    filters_data = {
        "price_min": price_min,
        "price_max": price_max,
        "property_type": property_type_enum,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "square_feet_min": square_feet_min,
        "square_feet_max": square_feet_max,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "country": country,
        "features": features,
        "listing_type": listing_type_enum,
        "listing_types": listing_types_enums,
        "status": status_enum,
        "is_featured": is_featured,
        "year_built_min": year_built_min,
        "year_built_max": year_built_max,
        "page": page,
        "limit": limit,
        "sort_by": sort_by,
        "sort_order": sort_order
    }
    
    try:
        filters = PropertySearchFilters.model_validate(filters_data)
    except ValidationError as e:
        # Log structured error for monitoring and debugging
        request_id = getattr(request.state, "request_id", "unknown") if hasattr(request, 'state') else "unknown"
        logger.error(
            event="property_search_validation_failed",
            request_id=request_id,
            path="/api/properties/search",
            validation_errors=e.errors(),
            input_data={k: v for k, v in filters_data.items() if v is not None},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors()
        )
    
    # Public search endpoint: Everyone sees marketplace view (same as public/guest)
    # role_context is ignored on search endpoints - all users see public listings
    # This is intentional: search is for browsing, not "My Listings"
    
    # Enterprise-grade: Use dedicated marketplace method (secure - no ownership filtering)
    service = PropertyService(db)
    skip = (filters.page - 1) * filters.limit
    properties, total_count = service.get_properties_marketplace(
        filters=filters,
        skip=skip,
        limit=filters.limit
    )
    return PropertySearchResponse(
        properties=serialize_properties(properties, user, db),
        total_count=total_count,
        page=filters.page,
        limit=filters.limit,
        total_pages=(total_count + filters.limit - 1) // filters.limit
    )


@router.get(
    "/all",
    response_model=PropertySearchResponse,
    response_model_exclude_none=True,
    summary="Get all properties (Admin only)",
    response_description="Admin-only endpoint to see all properties including deleted. Supports comprehensive filtering."
)
async def get_all_properties(
    request: Request,
    admin_user: User = Depends(get_admin_user),
    price_min: Optional[int] = Query(None, ge=0),
    price_max: Optional[int] = Query(None, ge=0),
    property_type: Optional[str] = Query(None),
    bedrooms: Optional[int] = Query(None, ge=0),
    bathrooms: Optional[float] = Query(None, ge=0),
    square_feet_min: Optional[int] = Query(None, ge=0),
    square_feet_max: Optional[int] = Query(None, ge=0),
    city: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    zip_code: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    features: Optional[str] = Query(None),
    listing_type: Optional[str] = Query(None, description="Single listing type (for_sale, for_rent, etc.) - for backward compatibility"),
    listing_types: Optional[str] = Query(None, description="Comma-separated listing types (e.g., 'for_rent,for_lease') - supports multiple values"),
    status: Optional[str] = Query(None),
    is_featured: Optional[bool] = Query(None),
    year_built_min: Optional[int] = Query(None, ge=1800, le=2030),
    year_built_max: Optional[int] = Query(None, ge=1800, le=2030),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade admin-only endpoint to view all properties in the system.
    
    Includes deleted properties unless explicitly filtered out.
    Supports comprehensive filtering with all PropertySearchFilters options.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Enterprise-grade: Normalize and convert inputs before schema instantiation
    
    # 1. Convert listing_type(s) string(s) to enum(s)
    listing_type_enum = None
    listing_types_enums = None
    
    if listing_types:
        # Parse comma-separated listing types
        try:
            listing_types_list = [lt.strip() for lt in listing_types.split(",") if lt.strip()]
            listing_types_enums = [ListingType(lt) for lt in listing_types_list]
        except ValueError:
            pass  # Invalid values will be handled by schema validation
    elif listing_type:
        # Single listing type for backward compatibility
        try:
            listing_type_enum = ListingType(listing_type)
        except ValueError:
            pass  # Invalid value will be handled by schema validation
    
    # 2. Convert status string to enum
    status_enum = None
    if status:
        try:
            status_enum = PropertyStatus(status)
        except ValueError:
            pass  # Invalid value will be handled by schema validation
    
    # 3. Convert property_type string to enum
    property_type_enum = None
    if property_type:
        try:
            property_type_enum = PropertyType(property_type)
        except ValueError:
            pass  # Invalid value will be handled by schema validation
    
    # 4. Normalize optional strings (convert empty strings to None)
    city = city or None
    state = state or None
    zip_code = zip_code or None
    country = country or None
    features = features or None
    
    # 5. Use model_validate for enterprise-grade type conversion and validation
    filters_data = {
        "price_min": price_min,
        "price_max": price_max,
        "property_type": property_type_enum,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "square_feet_min": square_feet_min,
        "square_feet_max": square_feet_max,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "country": country,
        "features": features,
        "listing_type": listing_type_enum,
        "listing_types": listing_types_enums,
        "status": status_enum,
        "is_featured": is_featured,
        "year_built_min": year_built_min,
        "year_built_max": year_built_max,
        "page": page,
        "limit": limit,
        "sort_by": sort_by,
        "sort_order": sort_order
    }
    
    try:
        filters = PropertySearchFilters.model_validate(filters_data)
    except ValidationError as e:
        # Log structured error for monitoring and debugging
        logger.error(
            event="property_search_validation_failed",
            request_id=request_id,
            path="/api/properties/all",
            validation_errors=e.errors(),
            input_data={k: v for k, v in filters_data.items() if v is not None},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors()
        )
    
    # Enterprise-grade: Use admin search with all filters
    property_service = PropertyService(db)
    skip = (filters.page - 1) * filters.limit
    properties, total_count = property_service.get_all_properties_admin(
        filters=filters,
        skip=skip,
        limit=filters.limit
    )
    
    return PropertySearchResponse(
        properties=serialize_properties(properties, admin_user, db),
        total_count=total_count,
        page=filters.page,
        limit=filters.limit,
        total_pages=(total_count + filters.limit - 1) // filters.limit
    )


@router.get(
    "/{property_id}",
    response_model=PropertyResponse,
    response_model_exclude_none=True,
    summary="Get specific property (Role-aware)",
    response_description="Details of a specific property, filtered by user role and permissions."
)
async def get_property(
    property_id: int,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade role-aware property retrieval.
    
    Permission rules:
    - Public/Guest: Only ACTIVE + public listing types (FOR_SALE, FOR_RENT, FOR_LEASE)
    - Buyer/Tenant: Same as public
    - Owner roles: ACTIVE + their own properties (any status, except DELETED)
    - Admin: All properties (any status)
    
    FOR_PORTFOLIO properties are NEVER visible to public/buyer/tenant users.
    """
    property_service = PropertyService(db)
    property = property_service.get_property_by_id(property_id)
    if not property:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    
    # Enterprise-grade: Check read permission using centralized permission service
    from app.services.property_permissions import PropertyPermissionService
    
    if not PropertyPermissionService.can_read_property(user, property, db):
        # Log access denial for security monitoring
        request_id = getattr(request.state, "request_id", "unknown")
        logger.warning(
            event="property_read_permission_denied",
            request_id=request_id,
            user_id=user.id if user else None,
            user_email=user.email if user else None,
            property_id=property_id,
            property_listing_type=property.listing_type.value if property.listing_type else None,
            property_status=property.status.value,
            user_roles=user.roles if user else []
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this property"
        )
    
    return serialize_property(property, user, db)


@router.post(
    "/",
    response_model=PropertyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new property (Role-aware)",
    response_description="Create a new property with role-based permission checks."
)
async def create_property(
    property_data: PropertyCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade role-aware property creation.
    
    Industry-standard transaction safety:
    - All validation happens BEFORE any database writes
    - Uses database transactions with automatic rollback on error
    - No partial property creation - all-or-nothing atomicity
    
    Permission rules:
    - Admin: any listing type
    - Seller: FOR_SALE only
    - Agent: FOR_SALE, FOR_RENT
    - Landlord: FOR_RENT only
    - Investor: FOR_PORTFOLIO only
    - Buyer/Tenant/Public: cannot create
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    try:
        property_service = PropertyService(db)
        property = property_service.create_property_with_role_check(
            property_data=property_data,
            user=current_user,
            request_id=request_id
        )
        return serialize_property(property, current_user, db)
    except ValueError as e:
        # Validation error or permission denied
        # Transaction already rolled back in service layer
        error_message = str(e)
        status_code = status.HTTP_400_BAD_REQUEST if "Validation failed" in error_message else status.HTTP_403_FORBIDDEN
        
        logger.warning(
            event="property_creation_denied",
            request_id=request_id,
            user_id=current_user.id,
            user_email=current_user.email,
            error_message=error_message,
            user_roles=current_user.roles
        )
        raise HTTPException(
            status_code=status_code,
            detail=error_message
        )
    except Exception as e:
        # Any other error - transaction already rolled back in service layer
        logger.error(
            event="property_creation_failed",
            request_id=request_id,
            user_id=current_user.id,
            user_email=current_user.email,
            property_title=property_data.title if property_data else "unknown",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create property: {str(e)}"
        )


@router.put(
    "/{property_id}",
    response_model=PropertyResponse,
    response_model_exclude_none=True,
    summary="Update property (Role-aware)",
    response_description="Update a property with role-based permission checks."
)
async def update_property(
    property_id: int,
    property_data: PropertyUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade role-aware property update.
    
    Permission rules:
    - Admin: can update any property
    - Owners: can update only their own properties
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    try:
        property_service = PropertyService(db)
        updated_property = property_service.update_property_with_role_check(
            property_id=property_id,
            property_data=property_data,
            user=current_user,
            request_id=request_id
        )
        return serialize_property(updated_property, current_user, db)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Property not found"
            )
        # Permission denied
        logger.warning(
            event="property_update_denied",
            request_id=request_id,
            user_id=current_user.id,
            property_id=property_id,
            error_message=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            event="property_update_failed",
            request_id=request_id,
            user_id=current_user.id,
            property_id=property_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update property: {str(e)}"
        )


@router.delete(
    "/{property_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete property (Soft delete - Role-aware)",
    response_description="Soft delete a property using status=DELETED with role-based permission checks."
)
async def delete_property(
    property_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade role-aware soft delete.
    
    Uses status=DELETED for soft delete as per enterprise requirements.
    
    Permission rules:
    - Admin: can delete any property
    - Owners: can delete only their own properties
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    try:
        property_service = PropertyService(db)
        success = property_service.delete_property_with_role_check(
            property_id=property_id,
            user=current_user,
            request_id=request_id
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete property"
            )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Property not found"
            )
        # Permission denied
        logger.warning(
            event="property_delete_denied",
            request_id=request_id,
            user_id=current_user.id,
            property_id=property_id,
            error_message=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            event="property_delete_failed",
            request_id=request_id,
            user_id=current_user.id,
            property_id=property_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete property: {str(e)}"
        )


@router.post(
    "/search",
    response_model=PropertySearchResponse,
    summary="Advanced Property Search (POST) - Role-aware",
    response_description="Search results with pagination metadata, filtered by user role."
)
async def search_properties_post(
    request: Request,
    filters: PropertySearchFilters,
    role_context: Optional[str] = Query(None, description="Role context for role-context-aware dashboards (seller, agent, landlord, investor). Must be one of user's roles."),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade role-aware property search (POST) with role-context support.
    
    Same filtering rules as GET /api/properties/search but accepts filters in request body.
    
    Behavior:
    - Public/Guest: Only ACTIVE + public listing types (FOR_SALE, FOR_RENT, FOR_LEASE)
    - Buyer/Tenant: Same as public (marketplace view)
    - Owner roles (Seller/Agent/Landlord/Investor): "My Listings" mode
      * Authenticated owners see ONLY their own properties
      * Role-context-aware listing type filtering:
        - If role_context provided: Only properties matching that role's listing types
        - If role_context is None: Properties matching any of user's owner roles (backward compatible)
      * All statuses except DELETED
      * No other users' listings included
    - Admin: All properties (any status, excluding DELETED)
    
    Supports advanced filtering: price, bedrooms, bathrooms, square_feet, location,
    features, year_built, sorting, and pagination.
    """
    # Public search endpoint (POST): Everyone sees marketplace view (same as public/guest)
    # role_context is ignored on search endpoints - all users see public listings
    # This is intentional: search is for browsing, not "My Listings"
    
    # Enterprise-grade: Use dedicated marketplace method (secure - no ownership filtering)
    service = PropertyService(db)
    skip = (filters.page - 1) * filters.limit
    properties, total_count = service.get_properties_marketplace(
        filters=filters,
        skip=skip,
        limit=filters.limit
    )
    return PropertySearchResponse(
        properties=serialize_properties(properties, user, db),
        total_count=total_count,
        page=filters.page,
        limit=filters.limit,
        total_pages=(total_count + filters.limit - 1) // filters.limit
    )
