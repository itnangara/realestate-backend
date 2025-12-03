"""
User Management Service for Admin Portal

Enterprise-grade service for admin user management operations:
- Create, read, update, deactivate users
- Role assignment and management
- Property assignment for maintenance staff and landlords
- Audit logging
- Email verification and welcome emails
"""

import secrets
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.user import User, UserStatus
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.user_property import UserProperty, RelationshipType
from app.models.property import Property
from app.schemas.admin_user import UserCreateAdmin, UserUpdateAdmin
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.services.role_service import RoleService
from app.services.audit_service import audit_service
from app.services.email_verification_service import EmailVerificationService
from app.services.notification_service import notification_service
from app.core.logger import get_logger
from app.services.profile_service import ProfileService

logger = get_logger(__name__)


class UserManagementService:
    """Service for admin user management operations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.user_service = UserService(db)
        self.auth_service = AuthService(db)
        self.role_service = RoleService(db)
        self.profile_service = ProfileService(db)
    
    def generate_password(self, length: int = 12) -> str:
        """Generate a secure random password"""
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def create_user(
        self,
        user_data: UserCreateAdmin,
        actor_id: int,
        request_id: Optional[str] = None
    ) -> User:
        """
        Create a new user with roles and property assignments.
        
        Args:
            user_data: User creation data
            actor_id: Admin user ID creating the user
            request_id: Optional request ID for audit logging
            
        Returns:
            Created User object
            
        Raises:
            HTTPException: If email/username already exists or validation fails
        """
        # Check if email already exists
        existing_user = self.user_service.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with email {user_data.email} already exists"
            )
        
        # Check if username already exists
        existing_username = self.user_service.get_user_by_username(user_data.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username {user_data.username} already taken"
            )
        
        # Generate password if not provided
        password = user_data.password or self.generate_password()
        hashed_password = self.auth_service.get_password_hash(password)
        
        # Create user object
        user = User(
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone=user_data.phone,
            status=user_data.status or UserStatus.PENDING,
            is_active=user_data.is_active if user_data.is_active is not None else True,
            is_verified=user_data.is_verified if user_data.is_verified is not None else False,
        )
        
        try:
            self.db.add(user)
            self.db.flush()  # Get user ID without committing
            
            # Assign roles
            if user_data.roles:
                self._assign_roles(user.id, user_data.roles)
                
                # Create profiles for roles that require them
                self.db.refresh(user)
                from sqlalchemy.orm import joinedload
                user_with_roles = self.db.query(User).options(
                    joinedload(User.user_roles)
                ).filter(User.id == user.id).first()
                
                if user_with_roles:
                    created_profiles = self.profile_service.create_profiles_for_roles(
                        user=user_with_roles,
                        roles=user_data.roles,
                        actor_id=actor_id,
                        request_id=request_id
                    )
                    if created_profiles:
                        logger.info(
                            "profiles_created_on_user_creation",
                            user_id=user.id,
                            profiles_created=created_profiles,
                            request_id=request_id
                        )
            
            # Assign properties
            if user_data.property_ids:
                self._assign_properties(user.id, user_data.property_ids)
            
            # Log audit
            audit_service.log_admin_action(
                db=self.db,
                action="user_created",
                admin_id=actor_id,
                target_type="user",
                target_id=user.id,
                meta={
                    "email": user.email,
                    "username": user.username,
                    "roles": user_data.roles,
                    "status": user.status.value,
                    "property_ids": user_data.property_ids or [],
                },
                request_id=request_id
            )
            
            # Send verification/welcome email
            try:
                verification_service = EmailVerificationService(self.db, notification_service)
                if not user.is_verified:
                    verification_service.send_verification_email(user, request_id)
                
                # Send welcome email with password if auto-generated
                if not user_data.password:
                    self._send_welcome_email(user, password, request_id)
            except Exception as e:
                # Log but don't fail user creation if email fails
                logger.error(
                    "welcome_email_failed",
                    user_id=user.id,
                    error=str(e),
                    request_id=request_id
                )
            
            self.db.commit()
            self.db.refresh(user)
            
            logger.info(
                "user_created_by_admin",
                admin_id=actor_id,
                user_id=user.id,
                email=user.email,
                roles=user_data.roles,
                request_id=request_id
            )
            
            return user
            
        except IntegrityError as e:
            self.db.rollback()
            logger.error(
                "user_creation_failed",
                error=str(e),
                email=user_data.email,
                request_id=request_id
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User creation failed due to database constraint violation"
            )
    
    def update_user(
        self,
        user_id: int,
        user_data: UserUpdateAdmin,
        actor_id: int,
        request_id: Optional[str] = None
    ) -> User:
        """
        Update user information, roles, and property assignments.
        
        Args:
            user_id: User ID to update
            user_data: Update data
            actor_id: Admin user ID performing the update
            request_id: Optional request ID for audit logging
            
        Returns:
            Updated User object
            
        Raises:
            HTTPException: If user not found or validation fails
        """
        user = self.user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        # Track changes for audit log
        changes = {}
        
        # Update basic fields
        if user_data.email and user_data.email != user.email:
            # Check if new email already exists
            existing = self.user_service.get_user_by_email(user_data.email)
            if existing and existing.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Email {user_data.email} already in use"
                )
            changes["email"] = {"old": user.email, "new": user_data.email}
            user.email = user_data.email
        
        if user_data.username and user_data.username != user.username:
            # Check if new username already exists
            existing = self.user_service.get_user_by_username(user_data.username)
            if existing and existing.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Username {user_data.username} already taken"
                )
            changes["username"] = {"old": user.username, "new": user_data.username}
            user.username = user_data.username
        
        if user_data.first_name is not None:
            user.first_name = user_data.first_name
        if user_data.last_name is not None:
            user.last_name = user_data.last_name
        if user_data.phone is not None:
            user.phone = user_data.phone
        if user_data.status is not None:
            changes["status"] = {"old": user.status.value, "new": user_data.status.value}
            user.status = user_data.status
        if user_data.is_active is not None:
            changes["is_active"] = {"old": user.is_active, "new": user_data.is_active}
            user.is_active = user_data.is_active
        if user_data.is_verified is not None:
            changes["is_verified"] = {"old": user.is_verified, "new": user_data.is_verified}
            user.is_verified = user_data.is_verified
        
        # Update roles if provided
        if user_data.roles is not None:
            old_roles = user.roles
            self._assign_roles(user.id, user_data.roles, replace=True)
            self.db.refresh(user)
            
            # Load user with roles relationship
            from sqlalchemy.orm import joinedload
            user_with_roles = self.db.query(User).options(
                joinedload(User.user_roles)
            ).filter(User.id == user_id).first()
            
            if user_with_roles:
                # Create profiles for newly assigned roles that require them
                created_profiles = self.profile_service.create_profiles_for_roles(
                    user=user_with_roles,
                    roles=user_data.roles,
                    actor_id=actor_id,
                    request_id=request_id
                )
                if created_profiles:
                    logger.info(
                        "profiles_created_on_role_update",
                        user_id=user.id,
                        profiles_created=created_profiles,
                        request_id=request_id
                    )
            
            self.db.refresh(user)
            changes["roles"] = {"old": old_roles, "new": user.roles}
        
        # Update property assignments if provided
        if user_data.property_ids is not None:
            old_property_ids = [up.property_id for up in self.db.query(UserProperty).filter(UserProperty.user_id == user_id).all()]
            self._assign_properties(user.id, user_data.property_ids, replace=True)
            changes["property_ids"] = {"old": old_property_ids, "new": user_data.property_ids}
        
        # Log audit
        audit_service.log_admin_action(
            db=self.db,
            action="user_updated",
            admin_id=actor_id,
            target_type="user",
            target_id=user_id,
            meta={"changes": changes},
            request_id=request_id
        )
        
        self.db.commit()
        self.db.refresh(user)
        
        logger.info(
            "user_updated_by_admin",
            admin_id=actor_id,
            user_id=user_id,
            changes=list(changes.keys()),
            request_id=request_id
        )
        
        return user
    
    def deactivate_user(
        self,
        user_id: int,
        actor_id: int,
        request_id: Optional[str] = None
    ) -> User:
        """
        Deactivate a user account.
        
        Args:
            user_id: User ID to deactivate
            actor_id: Admin user ID performing the action
            request_id: Optional request ID for audit logging
            
        Returns:
            Deactivated User object
            
        Raises:
            HTTPException: If user not found or trying to deactivate self
        """
        if user_id == actor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account"
            )
        
        user = self.user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        user.is_active = False
        
        # Log audit
        audit_service.log_admin_action(
            db=self.db,
            action="user_deactivated",
            admin_id=actor_id,
            target_type="user",
            target_id=user_id,
            meta={"email": user.email},
            request_id=request_id
        )
        
        self.db.commit()
        self.db.refresh(user)
        
        logger.info(
            "user_deactivated_by_admin",
            admin_id=actor_id,
            user_id=user_id,
            request_id=request_id
        )
        
        return user
    
    def activate_user(
        self,
        user_id: int,
        actor_id: int,
        request_id: Optional[str] = None
    ) -> User:
        """Activate a user account"""
        user = self.user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        user.is_active = True
        
        # Log audit
        audit_service.log_admin_action(
            db=self.db,
            action="user_activated",
            admin_id=actor_id,
            target_type="user",
            target_id=user_id,
            meta={"email": user.email},
            request_id=request_id
        )
        
        self.db.commit()
        self.db.refresh(user)
        
        return user
    
    def reset_password(
        self,
        user_id: int,
        new_password: str,
        actor_id: int,
        send_email: bool = True,
        request_id: Optional[str] = None
    ) -> User:
        """Reset user password"""
        user = self.user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        hashed_password = self.auth_service.get_password_hash(new_password)
        user.hashed_password = hashed_password
        
        # Log audit
        audit_service.log_admin_action(
            db=self.db,
            action="password_reset",
            admin_id=actor_id,
            target_type="user",
            target_id=user_id,
            meta={"email": user.email, "send_email": send_email},
            request_id=request_id
        )
        
        # Send password reset email if requested
        if send_email:
            try:
                # TODO: Implement password reset email
                pass
            except Exception as e:
                logger.error(
                    "password_reset_email_failed",
                    user_id=user_id,
                    error=str(e)
                )
        
        self.db.commit()
        self.db.refresh(user)
        
        return user
    
    def get_user_detail(self, user_id: int) -> Optional[User]:
        """Get detailed user information with relationships"""
        user = self.db.query(User).filter(User.id == user_id).first()
        return user
    
    def list_users(
        self,
        search: Optional[str] = None,
        role_filter: Optional[str] = None,
        status_filter: Optional[UserStatus] = None,
        is_active_filter: Optional[bool] = None,
        page: int = 1,
        limit: int = 25
    ) -> Tuple[List[User], int]:
        """
        List users with filters and pagination.
        
        Returns:
            Tuple of (users list, total count)
        """
        query = self.db.query(User)
        
        # Apply filters
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    User.email.ilike(search_term),
                    User.username.ilike(search_term),
                    User.first_name.ilike(search_term),
                    User.last_name.ilike(search_term),
                    User.phone.ilike(search_term)
                )
            )
        
        if status_filter:
            query = query.filter(User.status == status_filter)
        
        if is_active_filter is not None:
            query = query.filter(User.is_active == is_active_filter)
        
        if role_filter:
            # Filter by role using subquery to avoid join issues with eager loading
            role_user_ids = (
                self.db.query(UserRole.user_id)
                .join(Role)
                .filter(Role.name == role_filter)
                .distinct()
                .all()
            )
            user_ids = [uid[0] for uid in role_user_ids]
            if user_ids:
                query = query.filter(User.id.in_(user_ids))
            else:
                # No users with this role, return empty result
                query = query.filter(User.id == -1)  # Impossible condition
        
        # Get total count before eager loading
        total = query.count()
        
        # Eagerly load user_roles and roles for all queries
        query = query.options(joinedload(User.user_roles).joinedload(UserRole.role))
        
        # Apply pagination
        offset = (page - 1) * limit
        users = query.offset(offset).limit(limit).all()
        
        return users, total
    
    def get_user_audit_logs(
        self,
        user_id: int,
        limit: int = 50
    ) -> List:
        """Get audit logs for a specific user"""
        from app.models.audit_log import AuditLog
        
        logs = self.db.query(AuditLog).filter(
            or_(
                AuditLog.actor_id == user_id,
                and_(AuditLog.target_type == "user", AuditLog.target_id == user_id)
            )
        ).order_by(AuditLog.created_at.desc()).limit(limit).all()
        
        return logs
    
    def _assign_roles(self, user_id: int, role_names: List[str], replace: bool = False):
        """Assign roles to user"""
        if replace:
            # Remove existing roles
            self.db.query(UserRole).filter(UserRole.user_id == user_id).delete()
        
        # Get role objects
        roles = self.db.query(Role).filter(Role.name.in_(role_names)).all()
        if len(roles) != len(role_names):
            invalid_roles = set(role_names) - {role.name for role in roles}
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid roles: {', '.join(invalid_roles)}"
            )
        
        # Assign new roles (skip if already exists)
        existing_role_ids = {
            ur.role_id for ur in self.db.query(UserRole).filter(UserRole.user_id == user_id).all()
        }
        
        for role in roles:
            if role.id not in existing_role_ids:
                user_role = UserRole(user_id=user_id, role_id=role.id)
                self.db.add(user_role)
    
    def _assign_properties(self, user_id: int, property_ids: List[int], replace: bool = False):
        """
        Assign properties to user with appropriate relationship type.
        
        Determines relationship type based on user's roles:
        - Landlord -> LANDLORD
        - Maintenance Staff -> MAINTENANCE_STAFF
        - Agent -> AGENT
        - Investor -> INVESTOR
        - Tenant -> TENANT
        - Default -> MAINTENANCE_STAFF
        """
        from app.models.user_property import RelationshipType
        
        # Validate properties exist
        properties = self.db.query(Property).filter(Property.id.in_(property_ids)).all()
        if len(properties) != len(property_ids):
            invalid_ids = set(property_ids) - {p.id for p in properties}
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid property IDs: {', '.join(map(str, invalid_ids))}"
            )
        
        # Determine relationship type based on user roles
        user = self.user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        # Determine relationship type per new spec
        if user.has_role("landlord"):
            relationship_type = RelationshipType.LANDLORD
        elif user.has_role("maintenance_staff"):
            relationship_type = RelationshipType.MAINTENANCE_STAFF
        elif user.has_role("agent"):
            relationship_type = RelationshipType.AGENT
        elif user.has_role("investor"):
            relationship_type = RelationshipType.INVESTOR
        elif user.has_role("tenant"):
            relationship_type = RelationshipType.TENANT
        else:
            # Default to MAINTENANCE_STAFF for other roles
            relationship_type = RelationshipType.MAINTENANCE_STAFF
        
        if replace:
            # Remove existing assignments for this relationship type
            self.db.query(UserProperty).filter(
                UserProperty.user_id == user_id,
                UserProperty.relationship_type == relationship_type
            ).delete()
        
        # Assign new properties using PropertyAssignmentService for idempotency
        from app.services.property_assignment_service import PropertyAssignmentService
        assignment_service = PropertyAssignmentService(self.db)
        assignment_service.attach_properties(
            user_id=user_id,
            property_ids=property_ids,
            relationship_type=relationship_type
        )
    
    def _send_welcome_email(self, user: User, password: str, request_id: Optional[str] = None):
        """Send welcome email with password"""
        # TODO: Implement welcome email with password
        logger.info(
            "welcome_email_should_be_sent",
            user_id=user.id,
            email=user.email,
            request_id=request_id
        )

    # This is a hard delete user, it will delete the user & all its relationships
    def _hard_delete_user(self, user_id: int):
        user = self.user_service.get_user_by_id(user_id)
        print(f"Name: {user.first_name}, Email: {user.email}")
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
            print("user not found")
            return "user not found"

        user_id = user.id
        self.db.query(UserProperty).filter(UserProperty.user_id==user_id).delete(synchronize_session=False)
        self.db.query(UserRole).filter(UserRole.user_id==user_id).delete(synchronize_session=False)
        
        self.db.query(UserProperty).filter(
            UserProperty.user_id==user_id,
        ).delete(synchronize_session=False)
            
        print("delete_user: Isaac details, start")
        print(user)
        print("delete_user: Isaac details, end")
        # self.db.delete(user)
        self.db.commit()

