"""
Seller routes for real estate sellers
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.services.seller_service import SellerService
from app.schemas.seller import (
    SellerCreate,
    SellerUpdate,
    SellerResponse,
    SellerDetailResponse,
)
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/sellers", tags=["sellers"])

def get_seller_service(db: Session = Depends(get_db)) -> SellerService:
    """Dependency to inject SellerService"""
    return SellerService(db)

@router.post(
    "/",
    response_model=SellerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new seller",
    response_description="The created seller entry."
)
async def create_seller(
    seller_data: SellerCreate,
    current_user: User = Depends(get_current_user),
    service: SellerService = Depends(get_seller_service),
):
    """
    Create a new seller entry.
    
    - **name**: Seller's full name
    - **age**: Seller's age (optional)
    - **is_old**: Whether the seller is considered old
    """
    seller = service.create_seller(seller_data)
    return SellerResponse.from_orm(seller)

@router.get(
    "/",
    response_model=List[SellerResponse],
    response_model_exclude_none=True,
    summary="Get all sellers",
    response_description="List of all sellers in the system."
)
async def get_all_sellers(
    current_user: User = Depends(get_current_user),
    service: SellerService = Depends(get_seller_service),
):
    """
    Retrieve all sellers in the system.
    
    Returns a list of all sellers with their basic information.
    """
    sellers = service.get_all_sellers()
    return [SellerResponse.from_orm(seller) for seller in sellers]

@router.get(
    "/{seller_id}",
    response_model=SellerDetailResponse,
    response_model_exclude_none=True,
    summary="Get specific seller",
    response_description="Details of a specific seller."
)
async def get_seller(
    seller_id: int,
    current_user: User = Depends(get_current_user),
    service: SellerService = Depends(get_seller_service),
):
    """
    Retrieve a specific seller by ID.
    
    - **seller_id**: ID of the seller to retrieve
    """
    seller = service.get_seller_by_id(seller_id)
    if not seller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller not found")
    return SellerDetailResponse.from_orm(seller)

@router.put(
    "/{seller_id}",
    response_model=SellerResponse,
    response_model_exclude_none=True,
    summary="Update seller",
    response_description="The updated seller entry."
)
async def update_seller(
    seller_id: int,
    seller_data: SellerUpdate,
    current_user: User = Depends(get_current_user),
    service: SellerService = Depends(get_seller_service),
):
    """
    Update an existing seller.
    
    - **seller_id**: ID of the seller to update
    """
    seller = service.update_seller(seller_id, seller_data)
    if not seller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller not found")
    return SellerResponse.from_orm(seller)

@router.delete(
    "/{seller_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete seller",
    response_description="The seller has been successfully deleted."
)
async def delete_seller(
    seller_id: int,
    current_user: User = Depends(get_current_user),
    service: SellerService = Depends(get_seller_service),
):
    """
    Delete a seller.
    
    - **seller_id**: ID of the seller to delete
    """
    success = service.delete_seller(seller_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
