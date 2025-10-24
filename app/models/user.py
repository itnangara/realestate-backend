"""
Industry-standard User model for real estate application
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base
# Type hints are handled by SQLAlchemy Column definitions

# Role constants for consistency
class UserRoles:
    """User role constants"""
    BUYER = "buyer"
    SELLER = "seller"
    AGENT = "agent"
    LANDLORD = "landlord"
    TENANT = "tenant"
    INVESTOR = "investor"
    ADMIN = "admin"
    
    # All available roles
    ALL_ROLES = [BUYER, SELLER, AGENT, LANDLORD, TENANT, INVESTOR, ADMIN]

class User(Base):
    """User model optimized for multi-role system and FastAPI integration."""
    __tablename__ = "users"

    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    # Personal information
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    profile_image_url = Column(String(500), nullable=True)
    
    # User roles and permissions - multi-role support
    roles = Column(JSON, nullable=True, default=lambda: [])  # Array of roles: ["buyer", "agent", "investor"]
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_premium = Column(Boolean, default=False, nullable=False)
    
    # Professional information (for agents, landlords, etc.)
    company_name = Column(String(200), nullable=True)
    license_number = Column(String(100), nullable=True)  # For real estate agents
    bio = Column(Text, nullable=True)
    
    # Location and preferences
    preferred_locations = Column(JSON, nullable=True)  # Array of preferred cities/areas
    budget_min = Column(Integer, nullable=True)  # Minimum budget for buyers
    budget_max = Column(Integer, nullable=True)  # Maximum budget for buyers
    property_preferences = Column(JSON, nullable=True)  # Flexible property preferences
    
    # Activity tracking
    last_login = Column(DateTime(timezone=True), nullable=True)
    login_count = Column(Integer, default=0, nullable=False)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Audit trail
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    properties = relationship("Property", foreign_keys="Property.owner_id", back_populates="owner")
    applications = relationship("Application", foreign_keys="Application.applicant_id", back_populates="applicant")
    favorites = relationship("Favorite", foreign_keys="Favorite.user_id", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', roles={self.roles})>"
    
    @property
    def full_name(self) -> str:
        """Get user's full name"""
        return f"{self.first_name} {self.last_name}"
    
    def has_role(self, role: str) -> bool:
        """Check if user has a specific role"""
        if not self.roles:
            return False
        return role in self.roles
    
    def add_role(self, role: str) -> None:
        """Add a role to user"""
        if self.roles is None:
            self.roles = []
        if role not in self.roles:
            self.roles.append(role)
    
    def remove_role(self, role: str) -> None:
        """Remove a role from user"""
        if self.roles and role in self.roles:
            self.roles.remove(role)
    
    @property
    def is_agent(self) -> bool:
        """Check if user is a real estate agent"""
        return self.has_role(UserRoles.AGENT)
    
    @property
    def is_landlord(self) -> bool:
        """Check if user is a landlord"""
        return self.has_role(UserRoles.LANDLORD)
    
    @property
    def is_buyer(self) -> bool:
        """Check if user is a buyer"""
        return self.has_role(UserRoles.BUYER)
    
    @property
    def is_investor(self) -> bool:
        """Check if user is an investor"""
        return self.has_role(UserRoles.INVESTOR)
    
    @property
    def is_seller(self) -> bool:
        """Check if user is a seller"""
        return self.has_role(UserRoles.SELLER)
    
    @property
    def is_tenant(self) -> bool:
        """Check if user is a tenant"""
        return self.has_role(UserRoles.TENANT)
    
    @property
    def is_admin(self) -> bool:
        """Check if user is an admin"""
        return self.has_role(UserRoles.ADMIN)