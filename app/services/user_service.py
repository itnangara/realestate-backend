"""
User service for business logic
"""

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, List
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth_service import AuthService
from app.core.logger import get_logger

# Configure structured logger
logger = get_logger(__name__)

class UserService:
    """User service class"""
    
    def __init__(self, db: Session):
        self.db = db
        self.auth_service = AuthService(db)
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        return self.db.query(User).filter(User.id == user_id).first()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return self.db.query(User).filter(User.email == email).first()
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self.db.query(User).filter(User.username == username).first()
    
    def create_user(self, user_data: UserCreate) -> User:
        """Create a new user"""
        # Hash password
        hashed_password = self.auth_service.get_password_hash(user_data.password)
        
        # Create user object (exclude roles as it's a @property)
        user_data_dict = user_data.model_dump(exclude={'roles', 'password'})
        user = User(
            **user_data_dict,
            hashed_password=hashed_password
        )
        
        # Add to database
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        return user
    
    def update_user(self, user_id: int, user_data: UserUpdate) -> Optional[User]:
        """Update user information (excludes role changes - roles handled separately)"""
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        
        # Handle roles separately if provided (but warn about it)
        update_data = user_data.model_dump(exclude_unset=True)
        roles_to_update = update_data.pop('roles', None)
        
        # Warn if roles are provided in user update (should use dedicated endpoint)
        if roles_to_update is not None:
            # Log warning but don't process roles here
            logger.warning(
                "role_update_via_user_endpoint",
                user_id=user_id,
                attempted_roles=roles_to_update,
                message="Role changes attempted via user update. Use dedicated role endpoint.",
            )
        
        # Update other fields only
        for field, value in update_data.items():
            setattr(user, field, value)
        
        self.db.commit()
        self.db.refresh(user)
        
        return user
    
    def update_roles(self, user_id: int, role_names: List[str], return_user: bool = False):
        """Update user roles - dedicated role management (no dynamic role creation) with atomic transaction"""
        from app.models.role import Role
        from app.models.user_role import UserRole
        from fastapi import HTTPException
        
        # Fetch user with detailed error
        user = self.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=404, 
                detail=f"User with ID {user_id} not found"
            )
        
        # Validate role names exist in Role table (NO dynamic creation)
        roles = self.db.query(Role).filter(Role.name.in_(role_names)).all()
        if len(roles) != len(role_names):
            invalid_roles = set(role_names) - {role.name for role in roles}
            available_roles = [role.name for role in self.db.query(Role).all()]
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid role names: {', '.join(invalid_roles)}. Available roles: {', '.join(available_roles)}"
            )
        
        # Atomic transaction for role updates
        try:
            # Clear old roles
            self.db.query(UserRole).filter(UserRole.user_id == user_id).delete()
            
            # Assign new roles
            for role in roles:
                user_role = UserRole(user_id=user.id, role_id=role.id)
                self.db.add(user_role)
            
            # Commit transaction
            self.db.commit()
            logger.info(
                "roles_updated_successfully",
                user_id=user_id,
                updated_roles=[role.name for role in roles],
            )
            
        except SQLAlchemyError as e:
            # Rollback on error
            self.db.rollback()
            logger.error(
                "role_update_failed",
                user_id=user_id,
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to update roles due to database error"
            )
        
        # Return user object if requested, otherwise just role names
        if return_user:
            # Refresh user to get updated roles
            self.db.refresh(user)
            return {
                "user": user,
                "roles": [role.name for role in roles]
            }
        return [role.name for role in roles]
    
    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate user account"""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        
        user.is_active = False
        self.db.commit()
        return True