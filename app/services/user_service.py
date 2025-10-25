"""
User service for business logic
"""

from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth_service import AuthService

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
        
        # Create user object
        user = User(
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone=user_data.phone,
            roles=user_data.roles
        )
        
        # Add to database
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        return user
    
    def update_user(self, user_id: int, user_data: UserUpdate) -> Optional[User]:
        """Update user information"""
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        
        # Handle roles separately if provided
        update_data = user_data.model_dump(exclude_unset=True)
        roles_to_update = update_data.pop('roles', None)
        
        # Update other fields
        for field, value in update_data.items():
            setattr(user, field, value)
        
        # Handle role updates if provided
        if roles_to_update is not None:
            # Remove existing roles
            self.db.query(UserRole).filter(UserRole.user_id == user_id).delete()
            
            # Add new roles
            for role_name in roles_to_update:
                role = self.db.query(Role).filter(Role.name == role_name).first()
                if role:
                    user_role = UserRole(user_id=user_id, role_id=role.id)
                    self.db.add(user_role)
        
        self.db.commit()
        self.db.refresh(user)
        
        return user
    
    def update_roles(self, user_id: int, role_names: List[str]) -> List[str]:
        """Update user roles - dedicated role management"""
        from app.models.role import Role
        from app.models.user_role import UserRole
        from fastapi import HTTPException
        
        # Fetch user
        user = self.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Validate role names exist in Role table
        roles = self.db.query(Role).filter(Role.name.in_(role_names)).all()
        if len(roles) != len(role_names):
            invalid_roles = set(role_names) - {role.name for role in roles}
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid role names: {', '.join(invalid_roles)}"
            )
        
        # Clear old roles
        self.db.query(UserRole).filter(UserRole.user_id == user_id).delete()
        
        # Assign new roles
        for role in roles:
            user_role = UserRole(user_id=user.id, role_id=role.id)
            self.db.add(user_role)
        
        self.db.commit()
        return [role.name for role in roles]
    
    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate user account"""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        
        user.is_active = False
        self.db.commit()
        return True


