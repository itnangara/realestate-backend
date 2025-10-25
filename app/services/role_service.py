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

    def get_or_create_role(self, name: str):
        """Get existing role or create it if missing"""
        role = self.db.query(Role).filter_by(name=name).first()
        if not role:
            role = Role(name=name)
            self.db.add(role)
            self.db.commit()
            self.db.refresh(role)
        return role

    def assign_role_to_user(self, user_id: int, role_name: str):
        """Assign a role to a user"""
        role = self.get_or_create_role(role_name)
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
