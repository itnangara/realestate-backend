"""
Favorite service for business logic
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from app.models.favorite import Favorite
from app.schemas.favorite import FavoriteCreate

class FavoriteService:
    """Favorite service class"""
    
    def __init__(self, db: Session):
        self.db = db

    def get_favorite_by_id(self, favorite_id: int) -> Optional[Favorite]:
        return self.db.query(Favorite).filter(Favorite.id == favorite_id).first()

    def get_user_favorites(self, user_id: int) -> List[Favorite]:
        return self.db.query(Favorite).filter(Favorite.user_id == user_id).all()

    def create_favorite(self, favorite_data: FavoriteCreate, user_id: int) -> Favorite:
        existing_favorite = self.db.query(Favorite).filter(
            and_(Favorite.user_id == user_id, Favorite.property_id == favorite_data.property_id)
        ).first()
        
        if existing_favorite:
            return existing_favorite
        
        favorite = Favorite(
            user_id=user_id,
            property_id=favorite_data.property_id
        )
        self.db.add(favorite)
        self.db.commit()
        self.db.refresh(favorite)
        return favorite

    def delete_favorite(self, favorite_id: int, user_id: int) -> bool:
        favorite = self.db.query(Favorite).filter(
            and_(Favorite.id == favorite_id, Favorite.user_id == user_id)
        ).first()
        
        if not favorite:
            return False
        
        self.db.delete(favorite)
        self.db.commit()
        return True

    def is_favorite(self, user_id: int, property_id: int) -> bool:
        favorite = self.db.query(Favorite).filter(
            and_(Favorite.user_id == user_id, Favorite.property_id == property_id)
        ).first()
        return favorite is not None
