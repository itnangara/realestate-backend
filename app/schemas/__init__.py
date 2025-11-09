"""
Schemas package initialization
"""

from .user import (
    UserCreate, UserUpdate, UserOut, 
    UserLogin, Token, TokenData
)
from .property import (
    PropertyBase, PropertyCreate, PropertyUpdate, 
    PropertyResponse, PropertySearch
)
from .application import (
    ApplicationBase, ApplicationCreate, ApplicationUpdate,
    ApplicationResponse, ApplicationDetailResponse
)
from .document import (
    DocumentUploadRequest, DocumentUploadResponse,
    DocumentResponse, DocumentDownloadResponse, DocumentListResponse
)
from .role_request import (
    RoleRequestCreate, RoleRequestResponse, RoleRequestListResponse
)

__all__ = [
    # User schemas
    "UserCreate", 
    "UserUpdate",
    "UserOut",
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
    "ApplicationDetailResponse",
    
    # Document schemas
    "DocumentUploadRequest",
    "DocumentUploadResponse",
    "DocumentResponse",
    "DocumentDownloadResponse",
    "DocumentListResponse",
    
    # Role Request schemas
    "RoleRequestCreate",
    "RoleRequestResponse",
    "RoleRequestListResponse"
]


