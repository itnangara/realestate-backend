"""
Enterprise-grade authorization dependencies for FastAPI routes.

Provides reusable dependencies for role-based access control.
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.models.user import User
from app.dependencies.user_dependencies import get_current_user

# OAuth2 scheme for optional authentication
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False
)


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency that ensures the current user is an admin.
    
    Raises 403 Forbidden if user is not an admin.
    
    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(admin: User = Depends(get_admin_user)):
            ...
    """
    if not current_user.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Optional authentication dependency.
    
    Returns the authenticated user if a valid token is provided,
    otherwise returns None. This allows endpoints to work for both
    authenticated and unauthenticated users.
    
    Usage:
        @router.get("/public-or-authenticated")
        async def endpoint(user: Optional[User] = Depends(get_optional_user)):
            if user:
                # Authenticated user logic
            else:
                # Public/guest logic
    """
    if not token:
        return None
    
    try:
        auth_service = AuthService(db)
        email = auth_service.verify_token(token)
        user_service = UserService(db)
        user = user_service.get_user_by_email(email)
        return user
    except Exception:
        # Invalid token or user not found - treat as unauthenticated
        return None

