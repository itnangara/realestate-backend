"""
Enterprise-grade authorization dependencies for FastAPI routes.

Provides reusable dependencies for role-based access control.
"""

from typing import Optional, List, Union
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.models.user import User
from app.models.maintenance import MaintenanceRequest
from app.dependencies.user_dependencies import get_current_user
from app.core.logger import get_logger

logger = get_logger(__name__)

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


def require_role(*roles: str):
    """
    Enterprise-grade role-based access control dependency factory.
    
    Returns a dependency that ensures the current user has at least one of the specified roles.
    Raises 403 Forbidden if user doesn't have any of the required roles.
    
    Usage:
        @router.get("/staff-only")
        async def staff_endpoint(user: User = Depends(require_role("maintenance_staff"))):
            ...
        
        @router.get("/admin-or-staff")
        async def endpoint(user: User = Depends(require_role("admin", "maintenance_staff"))):
            ...
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        # Admin has access to everything
        if current_user.has_role("admin"):
            return current_user
        
        # Check if user has any of the required roles
        has_required_role = any(current_user.has_role(role) for role in roles)
        
        if not has_required_role:
            logger.warning(
                "access_denied_insufficient_role",
                user_id=current_user.id,
                user_email=current_user.email,
                required_roles=list(roles),
                user_roles=current_user.roles
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(roles)}"
            )
        
        return current_user
    
    return role_checker


def staff_scope_check(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> MaintenanceRequest:
    """
    Enterprise-grade scope checker for maintenance requests.
    
    Ensures that:
    - Maintenance staff can only access requests assigned to them
    - Tenants can only access their own requests
    - Landlords/Agents can access requests for their properties
    - Admins have full access
    
    Usage:
        @router.get("/{id}")
        async def get_request(request: MaintenanceRequest = Depends(staff_scope_check)):
            ...
    """
    from app.services.maintenance_service import MaintenanceService
    
    service = MaintenanceService(db)
    request = service.get_request_by_id(id)
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance request not found"
        )
    
    # Admin has full access
    if current_user.has_role("admin"):
        return request
    
    # Maintenance staff: only assigned requests
    if current_user.has_role("maintenance_staff"):
        if request.assigned_staff_id != current_user.id:
            logger.warning(
                "access_denied_staff_not_assigned",
                user_id=current_user.id,
                request_id=request_id,
                assigned_staff_id=request.assigned_staff_id
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. This request is not assigned to you."
            )
        return request
    
    # Tenant: only their own requests
    if current_user.has_role("tenant"):
        if request.tenant_id != current_user.id:
            logger.warning(
                "access_denied_tenant_not_owner",
                user_id=current_user.id,
                request_id=request_id,
                request_tenant_id=request.tenant_id
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. This request does not belong to you."
            )
        return request
    
    # Landlord/Agent: requests for their properties
    if current_user.has_role("landlord") or current_user.has_role("agent"):
        # Check if user owns/manages the property using unified ownership check
        from app.utils.property_ownership import is_property_owner
        from app.models.user_property import RelationshipType
        
        # Check ownership (LANDLORD relationship) or management (AGENT/ADMIN relationship)
        from app.models.user_property import UserProperty, RelationshipType
        
        has_access = (
            is_property_owner(db, current_user.id, request.property_id) or
            db.query(UserProperty).filter(
                UserProperty.user_id == current_user.id,
                UserProperty.property_id == request.property_id,
                UserProperty.relationship_type.in_([RelationshipType.AGENT, RelationshipType.ADMIN])
            ).first() is not None
        )
        
        if not has_access:
            logger.warning(
                "access_denied_landlord_not_owner",
                user_id=current_user.id,
                request_id=request_id,
                property_id=request.property_id
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. This request is for a property you don't manage."
            )
        return request
    
    # Default: deny access
    logger.warning(
        "access_denied_no_valid_role",
        user_id=current_user.id,
        user_roles=current_user.roles,
        request_id=request_id
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied. Insufficient permissions."
    )

