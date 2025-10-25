"""
Seller service for business logic
"""

from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.seller import Seller
from app.schemas.seller import SellerCreate, SellerUpdate

class SellerService:
    """Seller service class"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_seller_by_id(self, seller_id: int) -> Optional[Seller]:
        """Get seller by ID"""
        return self.db.query(Seller).filter(Seller.id == seller_id).first()
    
    def get_all_sellers(self) -> List[Seller]:
        """Get all sellers"""
        return self.db.query(Seller).all()
    
    def create_seller(self, seller_data: SellerCreate) -> Seller:
        """Create a new seller"""
        seller = Seller(
            name=seller_data.name,
            age=seller_data.age,
            is_old=seller_data.is_old
        )
        
        self.db.add(seller)
        self.db.commit()
        self.db.refresh(seller)
        
        return seller
    
    def update_seller(self, seller_id: int, seller_data: SellerUpdate) -> Optional[Seller]:
        """Update a seller"""
        seller = self.get_seller_by_id(seller_id)
        if not seller:
            return None
        
        update_data = seller_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(seller, field, value)
        
        self.db.commit()
        self.db.refresh(seller)
        
        return seller
    
    def delete_seller(self, seller_id: int) -> bool:
        """Delete a seller"""
        seller = self.get_seller_by_id(seller_id)
        if not seller:
            return False
        
        self.db.delete(seller)
        self.db.commit()
        return True
