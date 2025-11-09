"""
User routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.schemas.user import UserOut, UserUpdate, UserRolesUpdate
from app.services.user_service import UserService
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User
from app.core.logger import get_logger

# Configure structured logger
logger = get_logger(__name__)

router = APIRouter()

@router.get(
    "/me",
    response_model=UserOut,
    response_model_exclude_none=True,
    summary="Get current user profile",
    response_description="Profile information of the authenticated user."
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve the profile information of the authenticated user.
    
    Returns the user's profile data including personal information and preferences.
    """
    return current_user

@router.put(
    "/me",
    response_model=UserOut,
    response_model_exclude_none=True,
    summary="Update user profile",
    response_description="The updated user profile."
)
async def update_current_user(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the profile information of the authenticated user.
    
    **Note**: This endpoint does NOT allow role changes. Roles can only be modified by admins via /api/users/{id}/roles.
    
    - **first_name**: User's first name
    - **last_name**: User's last name
    - **phone**: Contact phone number
    - **profile_image_url**: URL to profile image
    - **company_name**: Company name (for agents)
    - **license_number**: Real estate license number
    - **bio**: User biography
    - **preferred_locations**: List of preferred locations
    - **budget_min**: Minimum budget preference
    - **budget_max**: Maximum budget preference
    - **property_preferences**: Property preference settings
    """
    user_service = UserService(db)
    updated_user = user_service.update_user(current_user.id, user_data)
    return updated_user

@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate user account",
    response_description="The user account has been successfully deactivated."
)
async def deactivate_current_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deactivate the authenticated user's account.
    
    This performs a soft delete - the account is deactivated but data is preserved.
    The user will no longer be able to log in.
    """
    user_service = UserService(db)
    success = user_service.deactivate_user(current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate account"
        )


@router.put(
    "/{user_id}/roles",
    response_model=List[str],
    summary="Update user roles",
    response_description="List of updated role names for the user."
)
async def update_user_roles(
    user_id: int,
    roles_data: UserRolesUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the roles of a user.
    
    - **user_id**: ID of the user to update roles for
    - **roles**: List of role names to assign to the user
    
    This endpoint:
    - Validates that all role names exist in the database
    - Removes existing role assignments
    - Assigns new roles to the user
    - Returns the list of assigned role names
    
    **Note**: This is a separate endpoint from user profile updates
    to maintain clear separation of concerns.
    
    **Admin-only**: Only users with admin role can modify user roles.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Admin-only restriction
    if not current_user.has_role("admin"):
        logger.warning(
            "unauthorized_role_update_attempt",
            request_id=request_id,
            admin_user_id=current_user.id,
            admin_email=current_user.email,
            target_user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can modify user roles"
        )
    
    user_service = UserService(db)
    
    # Get target user for logging
    target_user = user_service.get_user_by_id(user_id)
    if not target_user:
        logger.warning(
            "user_not_found_for_role_update",
            request_id=request_id,
            admin_user_id=current_user.id,
            target_user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Log admin action for audit trail
    logger.info(
        "role_update_initiated",
        request_id=request_id,
        admin_user_id=current_user.id,
        admin_email=current_user.email,
        target_user_id=user_id,
        target_user_email=target_user.email,
        requested_roles=roles_data.roles,
    )
    
    updated_roles = user_service.update_roles(user_id, roles_data.roles)
    
    # Log successful role update
    logger.info(
        "role_update_completed",
        request_id=request_id,
        admin_user_id=current_user.id,
        target_user_id=user_id,
        target_user_email=target_user.email,
        updated_roles=updated_roles,
    )
    
    return updated_roles