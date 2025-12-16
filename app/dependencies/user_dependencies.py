"""
User dependencies for FastAPI routes
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.utils.database import get_db
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.models.user import User
from app.models.user import User
from app.models.user_property import UserProperty, RelationshipType
from app.core.logger import get_logger

logger = get_logger(__name__)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user_email(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Get current user email from token"""
    auth_service = AuthService(db)
    return auth_service.verify_token(token)

def get_current_user(
    db: Session = Depends(get_db), 
    email: str = Depends(get_current_user_email)
) -> User:
    """
    Get current authenticated user.
    
    Enterprise-grade: Returns 401 (not 404) if user doesn't exist.
    This is a security issue - token references non-existent user.
    """
    user_service = UserService(db)
    user = user_service.get_user_by_email(email)
    
    if not user:
        # Enterprise-grade: Log security event for auditing
        logger.warning(
            "invalid_token_user_not_found",
            email=email,
            message="Token references non-existent user - possible deleted account or invalid token"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user

# -----------------------------------------------------
# 🟢 Authorization Dependencies for Specific Roles
# -----------------------------------------------------

def get_current_landlord_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db) # 💡 Added DB dependency for role lookup
) -> User:
    """
    Dependency that verifies the current user has the 'landlord' role 
    in the UserProperty mapping table (across any property).
    This enforces the authorization required for the /maintenance/staff endpoint.
    """
    # This checks if a user has *any* entry as a 'landlord' in any property context.
    is_landlord = db.query(UserProperty).filter(
        UserProperty.user_id == current_user.id,
        UserProperty.relationship_type == RelationshipType.LANDLORD
    ).first()
    
    if not is_landlord:
        logger.warning(
            "auth_violation",
            user_id=current_user.id,
            role="non-landlord",
            endpoint="/maintenance/staff",
            message="User attempted to access landlord-only endpoint without correct role."
        )
        # Return 403 Forbidden, not 401 Unauthorized
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource."
        )
    
    return current_user

def get_current_admin_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db) # DB dependency for role lookup
) -> User:
    """
    Dependency that verifies the current user has the 'admin' role 
    in the UserProperty mapping table (across any property).
    """
    # This checks if the user has *any* entry as an 'admin' (assuming global admin status).
    is_admin = db.query(UserProperty).filter(
        UserProperty.user_id == current_user.id,
        UserProperty.relationship_type == RelationshipType.ADMIN
    ).first()
    
    if not is_admin:
        # 🛡️ Return 403 Forbidden
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required."
        )
    return current_user
