"""
Role management routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.models.role import Role
from app.schemas.role import RoleListResponse
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User

router = APIRouter(tags=["Roles"])

@router.get(
    "/",
    response_model=List[RoleListResponse],
    summary="List all available system roles",
    response_description="List of all roles in the system (admin-only)."
)
async def list_roles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all available system roles.
    
    **Admin-only endpoint** - Only users with admin role can access this.
    
    Returns a list of all roles in the system with their details.
    """
    # Restrict to admin users only
    if not current_user.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Admin access required"
        )

    roles = db.query(Role).all()
    return roles
