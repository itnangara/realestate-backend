"""
Profile Service for Role-Specific Profile Management

Enterprise-grade service for automatically creating role-specific profiles
when users are assigned roles that require profiles.

Handles:
- Automatic profile creation for roles requiring profiles
- Idempotent operations (skip if profile exists)
- Audit logging
- Factory pattern for extensibility
"""

from sqlalchemy.orm import Session
from typing import List, Optional, Type, Dict
from datetime import datetime
from app.models.user import User
from app.models.tenant_profile import TenantProfile
from app.models.landlord_profile import LandlordProfile
from app.models.agent_profile import AgentProfile
from app.models.investor_profile import InvestorProfile
from app.models.maintenance_staff_profile import MaintenanceStaffProfile
from app.services.audit_service import audit_service
from app.core.logger import get_logger

logger = get_logger(__name__)


class ProfileService:
    """
    Service for managing role-specific profile creation.
    
    Uses factory pattern to map roles to profile classes,
    ensuring DRY principles and easy extensibility.
    """
    
    # Role to Profile Class mapping
    ROLE_TO_PROFILE_CLS: Dict[str, Type] = {
        "tenant": TenantProfile,
        "landlord": LandlordProfile,
        "agent": AgentProfile,
        "investor": InvestorProfile,
        "maintenance_staff": MaintenanceStaffProfile,
    }
    
    # Role to profile attribute name mapping
    ROLE_TO_PROFILE_ATTR: Dict[str, str] = {
        "tenant": "tenant_profile",
        "landlord": "landlord_profile",
        "agent": "agent_profile",
        "investor": "investor_profile",
        "maintenance_staff": "maintenance_staff_profile",
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_profiles_for_roles(
        self,
        user: User,
        roles: List[str],
        actor_id: Optional[int] = None,
        request_id: Optional[str] = None
    ) -> List[str]:
        """
        Create profiles for roles that require them.
        
        Args:
            user: User object
            roles: List of role names assigned to the user
            actor_id: Optional admin/actor ID for audit logging
            request_id: Optional request ID for audit correlation
            
        Returns:
            List of role names for which profiles were created
            
        Note:
            Idempotent - will skip creation if profile already exists.
        """
        created_profiles = []
        
        for role in roles:
            profile_cls = self.ROLE_TO_PROFILE_CLS.get(role)
            if not profile_cls:
                continue
            
            profile_attr = self.ROLE_TO_PROFILE_ATTR.get(role)
            if not profile_attr:
                continue
            
            # Check if profile already exists (idempotent)
            existing_profile = getattr(user, profile_attr, None)
            if existing_profile:
                logger.debug(
                    "profile_already_exists",
                    user_id=user.id,
                    role=role,
                    profile_id=existing_profile.id
                )
                continue
            
            # Create profile with default values
            try:
                # Handle special cases for profiles with required fields
                if role == "agent":
                    # AgentProfile requires license_number (non-nullable)
                    # Use a placeholder that can be updated later
                    profile = profile_cls(
                        user_id=user.id,
                        license_number=f"PENDING_{user.id}_{int(datetime.utcnow().timestamp())}",
                        license_state="PENDING"
                    )
                else:
                    profile = profile_cls(user_id=user.id)
                
                self.db.add(profile)
                self.db.flush()
                
                created_profiles.append(role)
                
                logger.info(
                    "profile_created",
                    user_id=user.id,
                    role=role,
                    profile_id=profile.id,
                    request_id=request_id
                )
                
                # Audit log profile creation
                if actor_id:
                    audit_service.log_admin_action(
                        db=self.db,
                        action="profile_created",
                        admin_id=actor_id,
                        target_type="profile",
                        target_id=profile.id,
                        meta={
                            "user_id": user.id,
                            "role": role,
                            "profile_type": profile_cls.__name__,
                        },
                        request_id=request_id
                    )
                    
            except Exception as e:
                logger.error(
                    "profile_creation_failed",
                    user_id=user.id,
                    role=role,
                    error=str(e),
                    request_id=request_id,
                    exc_info=True
                )
                # Continue with other roles even if one fails
                continue
        
        return created_profiles
    
    def ensure_profiles_for_user(
        self,
        user: User,
        actor_id: Optional[int] = None,
        request_id: Optional[str] = None
    ) -> List[str]:
        """
        Ensure profiles exist for all roles assigned to a user.
        
        Useful for:
        - Migrating existing users
        - Fixing missing profiles
        - Onboarding completion
        
        Args:
            user: User object (must have roles loaded)
            actor_id: Optional admin/actor ID for audit logging
            request_id: Optional request ID for audit correlation
            
        Returns:
            List of role names for which profiles were created
        """
        # Get user's roles
        user_roles = [ur.role.name for ur in user.user_roles] if hasattr(user, 'user_roles') else []
        
        if not user_roles:
            logger.debug(
                "no_roles_to_create_profiles",
                user_id=user.id
            )
            return []
        
        return self.create_profiles_for_roles(
            user=user,
            roles=user_roles,
            actor_id=actor_id,
            request_id=request_id
        )

