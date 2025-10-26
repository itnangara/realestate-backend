"""
Favorite routes for property favorites
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.services.favorite_service import FavoriteService
from app.dependencies.user_dependencies import get_current_user
from app.schemas.favorite import (
    FavoriteCreate,
    FavoriteResponse,
    FavoriteDetailResponse,
    FavoriteCheckResponse,
)
from app.models.user import User

router = APIRouter(tags=["Favorites"])

def get_favorite_service(db: Session = Depends(get_db)) -> FavoriteService:
    """Dependency to inject FavoriteService"""
    return FavoriteService(db)

@router.post(
    "/",
    response_model=FavoriteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add property to favorites",
    response_description="The created favorite entry."
)
async def create_favorite(
    favorite_data: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    service: FavoriteService = Depends(get_favorite_service),
):
    fav = service.create_favorite(favorite_data, current_user.id)
    return FavoriteResponse.model_validate(fav)

@router.get(
    "/",
    response_model=List[FavoriteDetailResponse],
    response_model_exclude_none=True,
    summary="Get user's favorite properties",
    response_description="List of properties favorited by the authenticated user."
)
async def get_user_favorites(
    current_user: User = Depends(get_current_user),
    service: FavoriteService = Depends(get_favorite_service),
):
    favs = service.get_user_favorites(current_user.id)
    return [FavoriteDetailResponse.model_validate(fav) for fav in favs]

@router.delete(
    "/{favorite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove property from favorites",
    response_description="The favorite has been successfully removed."
)
async def delete_favorite(
    favorite_id: int,
    current_user: User = Depends(get_current_user),
    service: FavoriteService = Depends(get_favorite_service),
):
    success = service.delete_favorite(favorite_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get(
    "/check/{property_id}",
    response_model=FavoriteCheckResponse,
    summary="Check if property is favorited",
    response_description="Returns whether the property is favorited by the user."
)
async def check_favorite(
    property_id: int,
    current_user: User = Depends(get_current_user),
    service: FavoriteService = Depends(get_favorite_service),
):
    is_fav = service.is_favorite(current_user.id, property_id)
    return FavoriteCheckResponse(is_favorite=is_fav)
