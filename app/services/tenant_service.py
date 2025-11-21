"""
Tenant service for tenant profile management
"""

from sqlalchemy.orm import Session
from typing import Optional
import json
from fastapi import HTTPException, status
from app.models.tenant_profile import TenantProfile
from app.models.user import User
from app.schemas.tenant import TenantProfileCreate, TenantProfileUpdate
from app.core.logger import get_logger

logger = get_logger(__name__)


class TenantService:
    """Service for tenant profile operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def _normalize_json_fields(self, profile: TenantProfile) -> TenantProfile:
        """Ensure JSON fields are always Python objects"""
        if profile.income_verification_documents:
            if isinstance(profile.income_verification_documents, str):
                try:
                    profile.income_verification_documents = json.loads(profile.income_verification_documents)
                except json.JSONDecodeError:
                    profile.income_verification_documents = []
        
        if profile.references:
            if isinstance(profile.references, str):
                try:
                    profile.references = json.loads(profile.references)
                except json.JSONDecodeError:
                    profile.references = []
        
        return profile
    
    def get_tenant_profile(self, user_id: int) -> Optional[TenantProfile]:
        """Get tenant profile by user ID"""
        profile = self.db.query(TenantProfile).filter(
            TenantProfile.user_id == user_id
        ).first()
        
        if profile:
            profile = self._normalize_json_fields(profile)
        
        return profile
    
    def create_tenant_profile(
        self,
        user_id: int,
        profile_data: TenantProfileCreate
    ) -> TenantProfile:
        """Create a new tenant profile"""
        # Check if user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if profile already exists
        existing_profile = self.get_tenant_profile(user_id)
        if existing_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant profile already exists. Use update endpoint instead."
            )
        
        # Create profile
        profile_dict = profile_data.model_dump(exclude_unset=True)
        profile = TenantProfile(
            user_id=user_id,
            **profile_dict
        )
        
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        
        logger.info(
            "tenant_profile_created",
            user_id=user_id,
            profile_id=profile.id
        )
        
        return self._normalize_json_fields(profile)
    
    def update_tenant_profile(
        self,
        user_id: int,
        profile_data: TenantProfileUpdate
    ) -> TenantProfile:
        """Update an existing tenant profile"""
        profile = self.get_tenant_profile(user_id)
        
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant profile not found. Create it first."
            )
        
        # Update fields
        update_data = profile_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(profile, field, value)
        
        self.db.commit()
        self.db.refresh(profile)
        
        logger.info(
            "tenant_profile_updated",
            user_id=user_id,
            profile_id=profile.id
        )
        
        return self._normalize_json_fields(profile)
    
    def create_or_update_tenant_profile(
        self,
        user_id: int,
        profile_data: TenantProfileCreate
    ) -> TenantProfile:
        """Create or update tenant profile (upsert)"""
        existing_profile = self.get_tenant_profile(user_id)
        
        if existing_profile:
            # Update existing
            update_data = TenantProfileUpdate(**profile_data.model_dump())
            return self.update_tenant_profile(user_id, update_data)
        else:
            # Create new
            return self.create_tenant_profile(user_id, profile_data)

