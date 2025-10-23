"""
Schemas package initialization
"""

from .user import (
    UserBase, UserCreate, UserUpdate, UserResponse, 
    UserLogin, Token, TokenData
)
from .property import (
    PropertyBase, PropertyCreate, PropertyUpdate, 
    PropertyResponse, PropertySearch
)
from .application import (
    ApplicationBase, ApplicationCreate, ApplicationUpdate,
    ApplicationResponse, ApplicationWithDetails
)

__all__ = [
    # User schemas
    "UserBase",
    "UserCreate", 
    "UserUpdate",
    "UserResponse",
    "UserLogin",
    "Token",
    "TokenData",
    
    # Property schemas
    "PropertyBase",
    "PropertyCreate",
    "PropertyUpdate", 
    "PropertyResponse",
    "PropertySearch",
    
    # Application schemas
    "ApplicationBase",
    "ApplicationCreate",
    "ApplicationUpdate",
    "ApplicationResponse", 
    "ApplicationWithDetails"
]


