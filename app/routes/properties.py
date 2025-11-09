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
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade role-aware property listing.
    
    Behavior:
    - Public/Guest: Only ACTIVE + public listing types (FOR_SALE, FOR_RENT, FOR_LEASE)
    - Buyer/Tenant: Same as public (marketplace view)
    - Owner roles (Seller/Agent/Landlord/Investor): "My Listings" mode
      * Authenticated owners see ONLY their own properties
      * Role-specific listing type filtering applied automatically:
        - Seller: only for_sale properties
        - Agent: only for_sale + for_rent properties
        - Landlord: only for_rent properties
        - Investor: only for_portfolio properties
      * All statuses except DELETED
      * No other users' listings included
    - Admin: All properties (any status, excluding DELETED - use /all endpoint to see deleted)
    
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
        limit=limit
    )
    
    return PropertySearchResponse(
        properties=[PropertyResponse.model_validate(p) for p in properties],
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
    status: Optional[str] = Query(None),
    is_featured: Optional[bool] = Query(None),
    year_built_min: Optional[int] = Query(None, ge=1800, le=2030),
    year_built_max: Optional[int] = Query(None, ge=1800, le=2030),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade role-aware property search (GET).
    
    Same filtering rules as GET /api/properties/ but with advanced filters:
    - Public/Guest: Only ACTIVE + public listing types (FOR_SALE, FOR_RENT, FOR_LEASE)
    - Buyer/Tenant: Same as public (marketplace view)
    - Owner roles (Seller/Agent/Landlord/Investor): "My Listings" mode
      * Authenticated owners see ONLY their own properties
      * Role-specific listing type filtering applied automatically
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
    
    # Enterprise-grade: Use role-aware search
    service = PropertyService(db)
    skip = (filters.page - 1) * filters.limit
    properties, total_count = service.get_properties_for_role(
        user=user,
        filters=filters,
        skip=skip,
        limit=filters.limit
    )
    return PropertySearchResponse(
        properties=[PropertyResponse.model_validate(p) for p in properties],
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
        properties=[PropertyResponse.model_validate(p) for p in properties],
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
    
    if not PropertyPermissionService.can_read_property(user, property):
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
            property_owner_id=property.owner_id,
            user_roles=user.roles if user else []
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this property"
        )
    
    return PropertyResponse.model_validate(property)


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
        return PropertyResponse.model_validate(property)
    except ValueError as e:
        # Permission denied or validation error
        logger.warning(
            event="property_creation_denied",
            request_id=request_id,
            user_id=current_user.id,
            user_email=current_user.email,
            error_message=str(e),
            user_roles=current_user.roles
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            event="property_creation_failed",
            request_id=request_id,
            user_id=current_user.id,
            user_email=current_user.email,
            property_title=property_data.title,
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
        return PropertyResponse.model_validate(updated_property)
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
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Enterprise-grade role-aware property search (POST).
    
    Same filtering rules as GET /api/properties/search but accepts filters in request body.
    
    Behavior:
    - Public/Guest: Only ACTIVE + public listing types (FOR_SALE, FOR_RENT, FOR_LEASE)
    - Buyer/Tenant: Same as public (marketplace view)
    - Owner roles (Seller/Agent/Landlord/Investor): "My Listings" mode
      * Authenticated owners see ONLY their own properties
      * Role-specific listing type filtering applied automatically
      * All statuses except DELETED
      * No other users' listings included
    - Admin: All properties (any status, excluding DELETED)
    
    Supports advanced filtering: price, bedrooms, bathrooms, square_feet, location,
    features, year_built, sorting, and pagination.
    """
    # Enterprise-grade: Use role-aware search
    service = PropertyService(db)
    skip = (filters.page - 1) * filters.limit
    properties, total_count = service.get_properties_for_role(
        user=user,
        filters=filters,
        skip=skip,
        limit=filters.limit
    )
    return PropertySearchResponse(
        properties=[PropertyResponse.model_validate(p) for p in properties],
        total_count=total_count,
        page=filters.page,
        limit=filters.limit,
        total_pages=(total_count + filters.limit - 1) // filters.limit
    )
