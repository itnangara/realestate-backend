"""
Property routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.utils.database import get_db
from app.schemas.property import PropertyResponse, PropertyCreate, PropertyUpdate, PropertySearch
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
    return property_service.get_properties(
        skip=skip,
        limit=limit,
        city=city,
        property_type=property_type,
        status=status,
        min_price=min_price,
        max_price=max_price
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
    
    return property

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
    return property

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
    return updated_property

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