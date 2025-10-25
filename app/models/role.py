"""
Role model for user role management
"""

from sqlalchemy import Column, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from app.utils.database import Base


class Role(Base):
    """Role model"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)

    # Relationships
    users = relationship("UserRole", back_populates="role", cascade="all, delete")

    def __repr__(self):
        return f"<Role(name='{self.name}')>"
