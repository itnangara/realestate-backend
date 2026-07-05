"""
Tenant service for tenant profile management
"""

from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional, List, Dict, Any, TypedDict
import json
from fastapi import HTTPException, status
from app.models.tenant_profile import TenantProfile
from app.models.user import User
from app.models.lease import Lease, LeaseStatus
from app.models import UserProperty
from app.models.property import Property
from app.schemas.tenant import TenantProfileCreate, TenantProfileUpdate
from app.core.logger import get_logger

logger = get_logger(__name__)

class TenantSummaryResponse(TypedDict):
    tenants: List[Dict[str, Any]]
    stats: Dict[str, Any]

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

    def get_tenants_for_landlord(
        self, 
        landlord_id: int, 
        status: str = None, 
        search: str = None
    ):
        # 1. Base Query with Joins
        # Join UserProperty to verify the landlord owns the property the tenant is in
        query = self.db.query(User, Lease, Property, TenantProfile)\
            .join(Lease, User.id == Lease.tenant_id)\
            .join(Property, Lease.property_id == Property.id)\
            .join(UserProperty, Property.id == UserProperty.property_id)\
            .outerjoin(TenantProfile, User.id == TenantProfile.user_id)

        # 2. Security: Filter by landlord ownership
        query = query.filter(UserProperty.user_id == landlord_id)

        # 3. Apply Filters
        if status and status != "all":
            query = query.filter(Lease.status == status)

        if search:
            search_filter = or_(
                User.first_name.ilike(f"%{search}%"), 
                User.last_name.ilike(f"%{search}%"), 
                User.email.ilike(f"%{search}%"),
                Property.title.ilike(f"%{search}%"),
            )
            query = query.filter(search_filter)

        results = query.all()

        tenants_list = []
        total_revenue = 0

        # 4. Transform Results
        for user, lease, prop, profile in results:
            if lease.status == LeaseStatus.COUNTER_SIGNED or lease.status == LeaseStatus.ACTIVE:
                total_revenue += (lease.rent or 0)
                print(f"Rent: {lease.rent}")

            tenants_list.append({
                "id": str(user.id),
                "name": f"{user.first_name} {user.last_name}",
                "email": user.email,
                "phone": getattr(profile, 'phone_number', "N/A") if profile else "N/A",
                "property_name": prop.title,
                "rent_amount": float(lease.rent) if lease.rent else 0,
                "lease_start": lease.start_date.isoformat() if lease.start_date else None, # Added
                "lease_end": lease.end_date.isoformat() if lease.end_date else None,
                "status": "active" if lease.status == "counter_signed" else lease.status,
            })

        return {
            "tenants": tenants_list,
            "stats": {
                "total_active": len([t for t in tenants_list if t['status'] == 'active']),
                "monthly_revenue": total_revenue,
                "delinquent_count": 0 
            }
        }