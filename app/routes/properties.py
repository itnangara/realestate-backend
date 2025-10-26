"""
Property routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.utils.database import get_db
from app.schemas.property import PropertyResponse, PropertyCreate, PropertyUpdate, PropertySearch, PropertySearchFilters, PropertySearchResponse
from app.services.property_service import PropertyService
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User

router = APIRouter()

@router.get(
    "/",
    response_model=List[PropertyResponse],
    response_model_exclude_none=True,
    summary="Get properties with filters",
    response_description="List of properties matching the specified filters."
)
async def get_properties(
    skip: int = Query(0, ge=0, description="Number of properties to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of properties to return"),
    city: Optional[str] = Query(None, description="Filter by city"),
    property_type: Optional[str] = Query(None, description="Filter by property type"),
    status: Optional[str] = Query(None, description="Filter by property status"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    db: Session = Depends(get_db)
):
    """
    Retrieve properties with optional filtering.
    
    - **skip**: Number of properties to skip (for pagination)
    - **limit**: Maximum number of properties to return (1-100)
    - **city**: Filter by city name
    - **property_type**: Filter by property type (house, apartment, etc.)
    - **status**: Filter by property status (for_sale, for_rent, etc.)
    - **min_price**: Minimum price filter
    - **max_price**: Maximum price filter
    """
    property_service = PropertyService(db)
    properties = property_service.get_properties(
        skip=skip,
        limit=limit,
        city=city,
        property_type=property_type,
        status=status,
        min_price=min_price,
        max_price=max_price
    )
    return [PropertyResponse.model_validate(property) for property in properties]

# --- Production-Grade Advanced Search Endpoints ---

@router.get(
    "/search",
    response_model=PropertySearchResponse,
    summary="Advanced Property Search (GET)",
    response_description="Search results with pagination metadata."
)
async def search_properties_get(
    price_min: Optional[int] = Query(None, ge=0, description="Minimum price"),
    price_max: Optional[int] = Query(None, ge=0, description="Maximum price"),
    property_type: Optional[str] = Query(None, description="Property type"),
    bedrooms: Optional[int] = Query(None, ge=0, description="Minimum bedrooms"),
    bathrooms: Optional[float] = Query(None, ge=0, description="Minimum bathrooms"),
    square_feet_min: Optional[int] = Query(None, ge=0, description="Minimum square feet"),
    square_feet_max: Optional[int] = Query(None, ge=0, description="Maximum square feet"),
    city: Optional[str] = Query(None, description="City name"),
    state: Optional[str] = Query(None, description="State"),
    zip_code: Optional[str] = Query(None, description="ZIP code"),
    country: Optional[str] = Query(None, description="Country"),
    features: Optional[str] = Query(None, description="Comma-separated features"),
    status: Optional[str] = Query(None, description="Property status"),
    is_featured: Optional[bool] = Query(None, description="Featured properties only"),
    year_built_min: Optional[int] = Query(None, ge=1800, le=2030, description="Minimum year built"),
    year_built_max: Optional[int] = Query(None, ge=1800, le=2030, description="Maximum year built"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    db: Session = Depends(get_db)
):
    """
    Advanced property search with comprehensive filtering options.
    
    **GET endpoint for simple queries** - Good for caching and bookmarking.
    
    - **price_min/max**: Price range filtering
    - **property_type**: Filter by property type (house, apartment, etc.)
    - **bedrooms/bathrooms**: Minimum room counts
    - **square_feet_min/max**: Size range filtering
    - **city/state/zip_code/country**: Location filtering
    - **features**: Comma-separated features (e.g., "pool,garage")
    - **status**: Property status (for_sale, for_rent, etc.)
    - **is_featured**: Show only featured properties
    - **year_built_min/max**: Year range filtering
    - **page/limit**: Pagination controls
    - **sort_by**: Sort field (price, created_at, bedrooms, etc.)
    - **sort_order**: Sort direction (asc, desc)
    """
    filters = PropertySearchFilters(
        price_min=price_min, price_max=price_max,
        property_type=property_type, bedrooms=bedrooms, bathrooms=bathrooms,
        square_feet_min=square_feet_min, square_feet_max=square_feet_max,
        city=city, state=state, zip_code=zip_code, country=country,
        features=features, status=status, is_featured=is_featured,
        year_built_min=year_built_min, year_built_max=year_built_max,
        page=page, limit=limit, sort_by=sort_by, sort_order=sort_order
    )
    
    service = PropertyService(db)
    properties, total_count = service.search_properties_advanced(filters)
    
    return PropertySearchResponse(
        properties=[PropertyResponse.model_validate(p) for p in properties],
        total_count=total_count,
        page=filters.page,
        limit=filters.limit,
        total_pages=(total_count + filters.limit - 1) // filters.limit
    )

@router.post(
    "/search",
    response_model=PropertySearchResponse,
    summary="Advanced Property Search (POST)",
    response_description="Search results with pagination metadata."
)
async def search_properties_post(
    filters: PropertySearchFilters,
    db: Session = Depends(get_db)
):
    """
    Advanced property search with comprehensive filtering options.
    
    **POST endpoint for complex queries** - Better for complex filter objects and arrays.
    
    Use this endpoint when you need to send complex filter objects or when
    the query parameters would be too long for a GET request.
    
    Same filtering options as GET endpoint but sent in request body.
    """
    service = PropertyService(db)
    properties, total_count = service.search_properties_advanced(filters)
    
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
    summary="Get specific property",
    response_description="Details of a specific property."
)
async def get_property(
    property_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve a specific property by ID.
    
    - **property_id**: ID of the property to retrieve
    """
    property_service = PropertyService(db)
    property = property_service.get_property_by_id(property_id)
    
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    return PropertyResponse.model_validate(property)

@router.post(
    "/",
    response_model=PropertyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new property",
    response_description="The created property entry."
)
async def create_property(
    property_data: PropertyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new property listing.
    
    - **title**: Property title
    - **description**: Property description
    - **property_type**: Type of property (house, apartment, etc.)
    - **status**: Property status (for_sale, for_rent, etc.)
    - **address**: Property address
    - **city**: City name
    - **state**: State/province
    - **zip_code**: Postal code
    - **country**: Country
    - **latitude**: GPS latitude
    - **longitude**: GPS longitude
    - **bedrooms**: Number of bedrooms
    - **bathrooms**: Number of bathrooms
    - **square_feet**: Property size in square feet
    - **lot_size**: Lot size in square feet
    - **year_built**: Year the property was built
    - **price**: Sale price
    - **rent_price**: Rental price
    - **features**: List of property features
    - **is_furnished**: Whether property is furnished
    - **pet_friendly**: Whether pets are allowed
    """
    property_service = PropertyService(db)
    property = property_service.create_property(property_data, current_user.id)
    return PropertyResponse.model_validate(property)

@router.put(
    "/{property_id}",
    response_model=PropertyResponse,
    response_model_exclude_none=True,
    summary="Update property",
    response_description="The updated property entry."
)
async def update_property(
    property_id: int,
    property_data: PropertyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing property.
    
    - **property_id**: ID of the property to update
    
    Only the property owner can update their properties.
    """
    property_service = PropertyService(db)
    
    # Check if property exists and user owns it
    property = property_service.get_property_by_id(property_id)
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if property.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Update property
    updated_property = property_service.update_property(property_id, property_data)
    return PropertyResponse.model_validate(updated_property)

@router.delete(
    "/{property_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete property",
    response_description="The property has been successfully deleted."
)
async def delete_property(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a property.
    
    - **property_id**: ID of the property to delete
    
    Only the property owner can delete their properties.
    This performs a soft delete - the property is deactivated but data is preserved.
    """
    property_service = PropertyService(db)
    
    # Check if property exists and user owns it
    property = property_service.get_property_by_id(property_id)
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    if property.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Delete property (soft delete)
    success = property_service.delete_property(property_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete property"
        )

@router.get(
    "/user/{user_id}",
    response_model=List[PropertyResponse],
    response_model_exclude_none=True,
    summary="Get user's properties",
    response_description="List of properties owned by the specified user."
)
async def get_user_properties(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve all properties owned by a specific user.
    
    - **user_id**: ID of the user whose properties to retrieve
    """
    property_service = PropertyService(db)
    properties = property_service.get_user_properties(user_id)
    return properties
@router.post(
    "/search",
    response_model=List[PropertyResponse],
    response_model_exclude_none=True,
    summary="Advanced property search",
    response_description="List of properties matching the advanced search criteria."
)
async def search_properties(
    search_filters: PropertySearch,
    db: Session = Depends(get_db)
):
    """
    Perform advanced property search with multiple filters.
    
    - **city**: Filter by city
    - **state**: Filter by state
    - **property_type**: Filter by property type
    - **status**: Filter by property status
    - **min_price**: Minimum price filter
    - **max_price**: Maximum price filter
    - **min_bedrooms**: Minimum number of bedrooms
    - **max_bedrooms**: Maximum number of bedrooms
    - **min_bathrooms**: Minimum number of bathrooms
    - **max_bathrooms**: Maximum number of bathrooms
    - **min_square_feet**: Minimum square footage
    - **max_square_feet**: Maximum square footage
    - **has_garage**: Filter by garage availability
    - **has_pool**: Filter by pool availability
    - **pet_friendly**: Filter by pet-friendly properties
    - **page**: Page number for pagination
    - **limit**: Number of results per page
    """
    property_service = PropertyService(db)
    search_dict = search_filters.model_dump(exclude_unset=True)
    properties = property_service.search_properties(search_dict)
    return properties

# --- Production-Grade Advanced Search Endpoints ---

@router.get(
    "/search",
    response_model=PropertySearchResponse,
    summary="Advanced Property Search (GET)",
    response_description="Search results with pagination metadata."
)
async def search_properties_get(
    price_min: Optional[int] = Query(None, ge=0, description="Minimum price"),
    price_max: Optional[int] = Query(None, ge=0, description="Maximum price"),
    property_type: Optional[str] = Query(None, description="Property type"),
    bedrooms: Optional[int] = Query(None, ge=0, description="Minimum bedrooms"),
    bathrooms: Optional[float] = Query(None, ge=0, description="Minimum bathrooms"),
    square_feet_min: Optional[int] = Query(None, ge=0, description="Minimum square feet"),
    square_feet_max: Optional[int] = Query(None, ge=0, description="Maximum square feet"),
    city: Optional[str] = Query(None, description="City name"),
    state: Optional[str] = Query(None, description="State"),
    zip_code: Optional[str] = Query(None, description="ZIP code"),
    country: Optional[str] = Query(None, description="Country"),
    features: Optional[str] = Query(None, description="Comma-separated features"),
    status: Optional[str] = Query(None, description="Property status"),
    is_featured: Optional[bool] = Query(None, description="Featured properties only"),
    year_built_min: Optional[int] = Query(None, ge=1800, le=2030, description="Minimum year built"),
    year_built_max: Optional[int] = Query(None, ge=1800, le=2030, description="Maximum year built"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    db: Session = Depends(get_db)
):
    """
    Advanced property search with comprehensive filtering options.
    
    **GET endpoint for simple queries** - Good for caching and bookmarking.
    
    - **price_min/max**: Price range filtering
    - **property_type**: Filter by property type (house, apartment, etc.)
    - **bedrooms/bathrooms**: Minimum room counts
    - **square_feet_min/max**: Size range filtering
    - **city/state/zip_code/country**: Location filtering
    - **features**: Comma-separated features (e.g., "pool,garage")
    - **status**: Property status (for_sale, for_rent, etc.)
    - **is_featured**: Show only featured properties
    - **year_built_min/max**: Year range filtering
    - **page/limit**: Pagination controls
    - **sort_by**: Sort field (price, created_at, bedrooms, etc.)
    - **sort_order**: Sort direction (asc, desc)
    """
    filters = PropertySearchFilters(
        price_min=price_min, price_max=price_max,
        property_type=property_type, bedrooms=bedrooms, bathrooms=bathrooms,
        square_feet_min=square_feet_min, square_feet_max=square_feet_max,
        city=city, state=state, zip_code=zip_code, country=country,
        features=features, status=status, is_featured=is_featured,
        year_built_min=year_built_min, year_built_max=year_built_max,
        page=page, limit=limit, sort_by=sort_by, sort_order=sort_order
    )
    
    service = PropertyService(db)
    properties, total_count = service.search_properties_advanced(filters)
    
    return PropertySearchResponse(
        properties=[PropertyResponse.model_validate(p) for p in properties],
        total_count=total_count,
        page=filters.page,
        limit=filters.limit,
        total_pages=(total_count + filters.limit - 1) // filters.limit
    )

@router.post(
    "/search",
    response_model=PropertySearchResponse,
    summary="Advanced Property Search (POST)",
    response_description="Search results with pagination metadata."
)
async def search_properties_post(
    filters: PropertySearchFilters,
    db: Session = Depends(get_db)
):
    """
    Advanced property search with comprehensive filtering options.
    
    **POST endpoint for complex queries** - Better for complex filter objects and arrays.
    
    Use this endpoint when you need to send complex filter objects or when
    the query parameters would be too long for a GET request.
    
    Same filtering options as GET endpoint but sent in request body.
    """
    service = PropertyService(db)
    properties, total_count = service.search_properties_advanced(filters)
    
    return PropertySearchResponse(
        properties=[PropertyResponse.model_validate(p) for p in properties],
        total_count=total_count,
        page=filters.page,
        limit=filters.limit,
        total_pages=(total_count + filters.limit - 1) // filters.limit
    )
