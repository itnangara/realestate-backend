"""
Property routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.utils.database import get_db
from app.schemas.property import PropertyResponse, PropertyCreate, PropertyUpdate, PropertySearch
from app.services.property_service import PropertyService
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.routes.auth import oauth2_scheme

router = APIRouter()

def get_current_user_email(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Get current user email from token"""
    auth_service = AuthService(db)
    return auth_service.verify_token(token)

@router.get("/", response_model=List[PropertyResponse])
async def get_properties(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    city: Optional[str] = None,
    property_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """Get properties with optional filters"""
    property_service = PropertyService(db)
    return property_service.get_properties(
        skip=skip,
        limit=limit,
        city=city,
        property_type=property_type,
        min_price=min_price,
        max_price=max_price
    )

@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific property by ID"""
    property_service = PropertyService(db)
    property = property_service.get_property_by_id(property_id)
    
    if not property:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )
    
    return property

@router.post("/", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
async def create_property(
    property_data: PropertyCreate,
    current_user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Create a new property"""
    property_service = PropertyService(db)
    user_service = UserService(db)
    
    # Get current user
    current_user = user_service.get_user_by_email(current_user_email)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Create property
    property = property_service.create_property(property_data, current_user.id)
    return property

@router.put("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: int,
    property_data: PropertyUpdate,
    current_user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Update a property"""
    property_service = PropertyService(db)
    user_service = UserService(db)
    
    # Get current user
    current_user = user_service.get_user_by_email(current_user_email)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
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

@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(
    property_id: int,
    current_user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Delete a property"""
    property_service = PropertyService(db)
    user_service = UserService(db)
    
    # Get current user
    current_user = user_service.get_user_by_email(current_user_email)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
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
    
    # Delete property
    property_service.delete_property(property_id)
