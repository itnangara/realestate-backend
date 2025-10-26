"""
Service for managing user roles
"""

from sqlalchemy.orm import Session
from app.models.role import Role
from app.models.user_role import UserRole


class RoleService:
    """Service class for role operations"""

    def __init__(self, db: Session):
        self.db = db

    def get_role_by_name(self, name: str):
        """Get existing role by name (no creation)"""
        return self.db.query(Role).filter_by(name=name).first()

    def assign_role_to_user(self, user_id: int, role_name: str):
        """Assign a role to a user (role must exist)"""
        role = self.get_role_by_name(role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' does not exist. Only predefined roles are allowed.")
        
        existing = self.db.query(UserRole).filter_by(user_id=user_id, role_id=role.id).first()
        if existing:
            return existing

        user_role = UserRole(user_id=user_id, role_id=role.id)
        self.db.add(user_role)
        self.db.commit()
        self.db.refresh(user_role)
        return user_role

    def get_user_roles(self, user_id: int):
        """List all roles for a user"""
        return self.db.query(UserRole).filter(UserRole.user_id == user_id).all()

    def remove_role_from_user(self, user_id: int, role_name: str):
        """Remove a role from a user"""
        role = self.db.query(Role).filter_by(name=role_name).first()
        if not role:
            return False
        user_role = self.db.query(UserRole).filter_by(user_id=user_id, role_id=role.id).first()
        if not user_role:
            return False
        self.db.delete(user_role)
        self.db.commit()
        return True
