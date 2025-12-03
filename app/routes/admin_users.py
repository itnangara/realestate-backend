"""
Admin User Management Routes

Enterprise-grade routes for admin user management:
- CRUD operations for users
- Role and property assignment
- Password reset
- Audit log viewing
- Bulk actions
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.utils.database import get_db
from app.schemas.admin_user import (
    UserCreateAdmin,
    UserUpdateAdmin,
    UserDetailAdmin,
    UserListItemAdmin,
    UserListResponse,
    PasswordResetRequest,
    BulkActionRequest,
    AuditLogEntry,
)
from app.services.user_management_service import UserManagementService
from app.dependencies.authorization_dependencies import get_admin_user
from app.models.user import User, UserStatus
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List users (admin only)",
    response_description="Paginated list of users with filters"
)
async def list_users(
    search: Optional[str] = Query(None, description="Search by name, email, username, or phone"),
    role: Optional[str] = Query(None, description="Filter by role name"),
    status_filter: Optional[UserStatus] = Query(None, description="Filter by user status"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(25, ge=1, le=100, description="Items per page"),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    List all users with optional filters and pagination.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    Query parameters:
    - search: Search by name, email, username, or phone
    - role: Filter by role name
    - status_filter: Filter by user status (pending, active, suspended, banned)
    - is_active: Filter by active status (true/false)
    - page: Page number (default: 1)
    - limit: Items per page (default: 25, max: 100)
    """
    service = UserManagementService(db)
    users, total = service.list_users(
        search=search,
        role_filter=role,
        status_filter=status_filter,
        is_active_filter=is_active,
        page=page,
        limit=limit
    )
    
    # Transform to response format
    user_items = []
    from app.models.user_property import UserProperty
    
    for user in users:
        # Get assigned properties count from unified user_properties table
        # This includes owners, maintenance staff, and all other relationship types
        assigned_count = db.query(UserProperty).filter(UserProperty.user_id == user.id).count()
        
        user_items.append(UserListItemAdmin(
            id=user.id,
            email=user.email,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=user.full_name,
            phone=user.phone,
            roles=user.roles,
            status=user.status,
            is_active=user.is_active,
            is_verified=user.is_verified,
            last_login=user.last_login,
            assigned_properties_count=assigned_count,
            created_at=user.created_at
        ))
    
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    
    logger.info(
        "admin_users_listed",
        admin_user_id=admin_user.id,
        total=total,
        returned=len(user_items),
        page=page
    )
    
    return UserListResponse(
        users=user_items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages
    )


@router.get(
    "/users/{user_id}",
    response_model=UserDetailAdmin,
    summary="Get user details (admin only)",
    response_description="Detailed user information with roles and property assignments"
)
async def get_user(
    user_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific user.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    Returns:
    - User details
    - Assigned roles
    - Assigned properties
    - Activity information
    """
    service = UserManagementService(db)
    user = service.get_user_detail(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Get assigned properties
    from app.models.user_property import UserProperty
    from app.schemas.admin_user import UserPropertyAssignment
    
    from app.models.property import Property
    # Enterprise-grade: Query properties directly with explicit column selection to avoid JSON comparison issues
    user_properties = db.query(UserProperty).filter(UserProperty.user_id == user_id).all()
    assigned_properties = []
    for up in user_properties:
        property_obj = (
            db.query(Property.id, Property.title, Property.address)
            .filter(Property.id == up.property_id)
            .first()
        )
        if property_obj:
            assigned_properties.append(UserPropertyAssignment(
                property_id=up.property_id,
                property_title=property_obj.title,
                property_address=property_obj.address
            ))
    
    return UserDetailAdmin(
        id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        profile_image_url=user.profile_image_url,
        roles=user.roles,
        status=user.status,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_premium=user.is_premium,
        assigned_properties=assigned_properties,
        last_login=user.last_login,
        login_count=user.login_count,
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.post(
    "/users",
    response_model=UserDetailAdmin,
    status_code=status.HTTP_201_CREATED,
    summary="Create user (admin only)",
    response_description="Newly created user"
)
async def create_user(
    user_data: UserCreateAdmin,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Create a new user with roles and property assignments.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    This endpoint:
    - Creates a new user account
    - Assigns specified roles
    - Assigns properties (for maintenance_staff/landlord roles)
    - Sends verification/welcome email
    - Logs the action in audit trail
    
    Business rules:
    - Email must be unique
    - Username must be unique
    - Password is auto-generated if not provided
    - Admin role creation may be restricted (check super-admin requirements)
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = UserManagementService(db)
    user = service.create_user(
        user_data=user_data,
        actor_id=admin_user.id,
        request_id=request_id
    )
    
    # Get assigned properties for response
    from app.models.user_property import UserProperty
    from app.models.property import Property
    from app.schemas.admin_user import UserPropertyAssignment
    
    # Enterprise-grade: Query properties directly to avoid JSON column issues
    # Select only needed columns to avoid DISTINCT on JSON fields
    user_properties = db.query(UserProperty).filter(UserProperty.user_id == user.id).all()
    assigned_properties = []
    for up in user_properties:
        # Query Property directly with explicit column selection to avoid JSON comparison issues
        property_obj = (
            db.query(Property.id, Property.title, Property.address)
            .filter(Property.id == up.property_id)
            .first()
        )
        if property_obj:
            assigned_properties.append(UserPropertyAssignment(
                property_id=up.property_id,
                property_title=property_obj.title,
                property_address=property_obj.address
            ))
    
    return UserDetailAdmin(
        id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        profile_image_url=user.profile_image_url,
        roles=user.roles,
        status=user.status,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_premium=user.is_premium,
        assigned_properties=assigned_properties,
        last_login=user.last_login,
        login_count=user.login_count,
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.patch(
    "/users/{user_id}",
    response_model=UserDetailAdmin,
    summary="Update user (admin only)",
    response_description="Updated user information"
)
async def update_user(
    user_id: int,
    user_data: UserUpdateAdmin,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Update user information, roles, and property assignments.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    This endpoint:
    - Updates user fields
    - Updates roles (replaces existing)
    - Updates property assignments (replaces existing)
    - Logs all changes in audit trail
    
    Business rules:
    - Cannot update email/username to values already in use
    - Cannot deactivate your own account
    - Role changes trigger permission updates
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = UserManagementService(db)
    user = service.update_user(
        user_id=user_id,
        user_data=user_data,
        actor_id=admin_user.id,
        request_id=request_id
    )
    
    # Get assigned properties for response
    from app.models.user_property import UserProperty
    from app.schemas.admin_user import UserPropertyAssignment
    
    from app.models.property import Property
    # Enterprise-grade: Query properties directly with explicit column selection to avoid JSON comparison issues
    user_properties = db.query(UserProperty).filter(UserProperty.user_id == user_id).all()
    assigned_properties = []
    for up in user_properties:
        property_obj = (
            db.query(Property.id, Property.title, Property.address)
            .filter(Property.id == up.property_id)
            .first()
        )
        if property_obj:
            assigned_properties.append(UserPropertyAssignment(
                property_id=up.property_id,
                property_title=property_obj.title,
                property_address=property_obj.address
            ))
    
    return UserDetailAdmin(
        id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        profile_image_url=user.profile_image_url,
        roles=user.roles,
        status=user.status,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_premium=user.is_premium,
        assigned_properties=assigned_properties,
        last_login=user.last_login,
        login_count=user.login_count,
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.post(
    "/users/{user_id}/deactivate",
    response_model=UserDetailAdmin,
    summary="Deactivate user (admin only)",
    response_description="Deactivated user"
)
async def deactivate_user(
    user_id: int,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Deactivate a user account.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    This endpoint:
    - Sets user.is_active = False
    - Prevents user from logging in
    - Keeps all history and assignments intact
    - Logs the action in audit trail
    
    Business rules:
    - Cannot deactivate your own account
    - Cannot deactivate last admin (if implemented)
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = UserManagementService(db)
    user = service.deactivate_user(
        user_id=user_id,
        actor_id=admin_user.id,
        request_id=request_id
    )
    
    # Return simplified response
    from app.models.user_property import UserProperty
    from app.schemas.admin_user import UserPropertyAssignment
    
    from app.models.property import Property
    # Enterprise-grade: Query properties directly with explicit column selection to avoid JSON comparison issues
    user_properties = db.query(UserProperty).filter(UserProperty.user_id == user_id).all()
    assigned_properties = []
    for up in user_properties:
        property_obj = (
            db.query(Property.id, Property.title, Property.address)
            .filter(Property.id == up.property_id)
            .first()
        )
        if property_obj:
            assigned_properties.append(UserPropertyAssignment(
                property_id=up.property_id,
                property_title=property_obj.title,
                property_address=property_obj.address
            ))
    
    return UserDetailAdmin(
        id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        profile_image_url=user.profile_image_url,
        roles=user.roles,
        status=user.status,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_premium=user.is_premium,
        assigned_properties=assigned_properties,
        last_login=user.last_login,
        login_count=user.login_count,
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.post(
    "/users/{user_id}/activate",
    response_model=UserDetailAdmin,
    summary="Activate user (admin only)",
    response_description="Activated user"
)
async def activate_user(
    user_id: int,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Activate a user account"""
    request_id = getattr(request.state, 'request_id', None)
    
    service = UserManagementService(db)
    user = service.activate_user(
        user_id=user_id,
        actor_id=admin_user.id,
        request_id=request_id
    )
    
    # Return simplified response
    from app.models.user_property import UserProperty
    from app.schemas.admin_user import UserPropertyAssignment
    
    from app.models.property import Property
    # Enterprise-grade: Query properties directly with explicit column selection to avoid JSON comparison issues
    user_properties = db.query(UserProperty).filter(UserProperty.user_id == user_id).all()
    assigned_properties = []
    for up in user_properties:
        property_obj = (
            db.query(Property.id, Property.title, Property.address)
            .filter(Property.id == up.property_id)
            .first()
        )
        if property_obj:
            assigned_properties.append(UserPropertyAssignment(
                property_id=up.property_id,
                property_title=property_obj.title,
                property_address=property_obj.address
            ))
    
    return UserDetailAdmin(
        id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        profile_image_url=user.profile_image_url,
        roles=user.roles,
        status=user.status,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_premium=user.is_premium,
        assigned_properties=assigned_properties,
        last_login=user.last_login,
        login_count=user.login_count,
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.post(
    "/users/{user_id}/reset-password",
    response_model=UserDetailAdmin,
    summary="Reset user password (admin only)",
    response_description="User with reset password"
)
async def reset_password(
    user_id: int,
    password_data: PasswordResetRequest,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Reset a user's password.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    This endpoint:
    - Sets a new password for the user
    - Optionally sends password reset email
    - Logs the action in audit trail
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = UserManagementService(db)
    user = service.reset_password(
        user_id=user_id,
        new_password=password_data.new_password,
        actor_id=admin_user.id,
        send_email=password_data.send_email,
        request_id=request_id
    )
    
    # Return simplified response
    from app.models.user_property import UserProperty
    from app.schemas.admin_user import UserPropertyAssignment
    
    from app.models.property import Property
    # Enterprise-grade: Query properties directly with explicit column selection to avoid JSON comparison issues
    user_properties = db.query(UserProperty).filter(UserProperty.user_id == user_id).all()
    assigned_properties = []
    for up in user_properties:
        property_obj = (
            db.query(Property.id, Property.title, Property.address)
            .filter(Property.id == up.property_id)
            .first()
        )
        if property_obj:
            assigned_properties.append(UserPropertyAssignment(
                property_id=up.property_id,
                property_title=property_obj.title,
                property_address=property_obj.address
            ))
    
    return UserDetailAdmin(
        id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        profile_image_url=user.profile_image_url,
        roles=user.roles,
        status=user.status,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_premium=user.is_premium,
        assigned_properties=assigned_properties,
        last_login=user.last_login,
        login_count=user.login_count,
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.get(
    "/users/{user_id}/audit",
    response_model=List[AuditLogEntry],
    summary="Get user audit logs (admin only)",
    response_description="List of audit log entries for the user"
)
async def get_user_audit_logs(
    user_id: int,
    limit: int = Query(50, ge=1, le=200, description="Maximum number of logs to return"),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get audit logs for a specific user.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    Returns:
    - All actions performed by the user (as actor)
    - All actions performed on the user (as target)
    """
    service = UserManagementService(db)
    logs = service.get_user_audit_logs(user_id, limit=limit)
    
    return [AuditLogEntry.model_validate(log) for log in logs]


@router.post(
    "/users/bulk-action",
    summary="Bulk user actions (admin only)",
    response_description="Bulk action result"
)
async def bulk_action(
    bulk_data: BulkActionRequest,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    Perform bulk actions on multiple users.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    Supported actions:
    - activate: Activate multiple users
    - deactivate: Deactivate multiple users
    - assign_properties: Assign properties to multiple users (requires property_ids)
    
    Business rules:
    - Cannot deactivate yourself
    - Cannot deactivate last admin (if implemented)
    """
    request_id = getattr(request.state, 'request_id', None)
    service = UserManagementService(db)
    
    results = {
        "success": [],
        "failed": []
    }
    
    for user_id in bulk_data.user_ids:
        try:
            if bulk_data.action == "activate":
                service.activate_user(user_id, admin_user.id, request_id)
                results["success"].append(user_id)
            elif bulk_data.action == "deactivate":
                if user_id == admin_user.id:
                    results["failed"].append({"user_id": user_id, "reason": "Cannot deactivate yourself"})
                else:
                    service.deactivate_user(user_id, admin_user.id, request_id)
                    results["success"].append(user_id)
            elif bulk_data.action == "assign_properties":
                if not bulk_data.property_ids:
                    results["failed"].append({"user_id": user_id, "reason": "property_ids required"})
                else:
                    # Update user with property assignments
                    from app.schemas.admin_user import UserUpdateAdmin
                    update_data = UserUpdateAdmin(property_ids=bulk_data.property_ids)
                    service.update_user(user_id, update_data, admin_user.id, request_id)
                    results["success"].append(user_id)
            else:
                results["failed"].append({"user_id": user_id, "reason": f"Unknown action: {bulk_data.action}"})
        except Exception as e:
            results["failed"].append({"user_id": user_id, "reason": str(e)})
    
    return {
        "action": bulk_data.action,
        "total": len(bulk_data.user_ids),
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
        "success": results["success"],
        "failed": results["failed"]
    }

