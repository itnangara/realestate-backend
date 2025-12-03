"""
Role Granting Service for managing role assignments

Handles:
- Granting roles to users
- Updating role request status
- Sending notifications
- Integration with audit service
"""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
from datetime import datetime
from fastapi import HTTPException, status

from app.models.role_request import RoleRequest, RoleRequestStatus
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.user import User
from app.services.role_service import RoleService
from app.services.profile_service import ProfileService
from app.services.notification_service import notification_service
from app.services.audit_service import audit_service
from app.core.logger import get_logger

logger = get_logger(__name__)


class RoleGrantingService:
    """Service for role granting operations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.role_service = RoleService(db)
        self.profile_service = ProfileService(db)
    
    def grant_roles(
        self,
        user_id: int,
        role_names: List[str],
        role_request_id: Optional[int] = None,
        granted_by: Optional[int] = None,
        request_id: Optional[str] = None
    ) -> dict:
        """
        Grant roles to a user with transactional safety.
        
        Enterprise-grade: Wraps entire operation in a single transaction.
        If profile creation fails, rolls back role assignments to prevent
        inconsistent state.
        
        Args:
            user_id: ID of the user to grant roles to
            role_names: List of role names to grant
            role_request_id: Optional associated role request ID
            granted_by: Optional admin user ID who granted the roles
            request_id: Optional request ID for correlation
            
        Returns:
            Dictionary with granted_roles and skipped_roles
            
        Raises:
            HTTPException: If validation fails or transaction fails
        """
        granted_roles = []
        skipped_roles = []
        profile_creation_failed = False
        
        try:
            # Step 1: Validate and assign roles
            for role_name in role_names:
                try:
                    # Check if user already has this role
                    existing_roles = self.role_service.get_user_roles(user_id)
                    role = self.role_service.get_role_by_name(role_name)
                    
                    if not role:
                        skipped_roles.append({
                            "role": role_name,
                            "reason": "Role does not exist"
                        })
                        continue
                    
                    # Check if already assigned
                    if any(ur.role_id == role.id for ur in existing_roles):
                        skipped_roles.append({
                            "role": role_name,
                            "reason": "Already assigned"
                        })
                        continue
                    
                    # Assign role
                    self.role_service.assign_role_to_user(user_id, role_name)
                    granted_roles.append(role_name)
                    
                    logger.info(
                        "role_granted",
                        user_id=user_id,
                        role_name=role_name,
                        role_request_id=role_request_id
                    )
                    
                except Exception as e:
                    logger.error(
                        "role_grant_failed",
                        user_id=user_id,
                        role_name=role_name,
                        error=str(e)
                    )
                    skipped_roles.append({
                        "role": role_name,
                        "reason": str(e)
                    })
            
            # Step 2: Create profiles for roles that require them
            if granted_roles:
                # Load user with roles relationship using joinedload
                user = self.db.query(User).options(
                    joinedload(User.user_roles)
                ).filter(User.id == user_id).first()
                
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"User with ID {user_id} not found"
                    )
                
                created_profiles = self.profile_service.create_profiles_for_roles(
                    user=user,
                    roles=granted_roles,
                    actor_id=granted_by,
                    request_id=request_id
                )
                
                if created_profiles:
                    logger.info(
                        "profiles_created_on_role_grant",
                        user_id=user_id,
                        profiles_created=created_profiles,
                        role_request_id=role_request_id,
                        request_id=request_id
                    )
                
                # Check if all required profiles were created
                # If profile creation failed for any role, we should rollback
                # (ProfileService logs errors but continues - we check here)
                required_profiles = [
                    role for role in granted_roles 
                    if role in self.profile_service.ROLE_TO_PROFILE_CLS
                ]
                if required_profiles and not created_profiles:
                    # No profiles created but profiles were required
                    profile_creation_failed = True
                    logger.error(
                        "profile_creation_failed_for_all_roles",
                        user_id=user_id,
                        required_roles=required_profiles,
                        request_id=request_id
                    )
            
            # Step 3: Update role request status if provided
            if role_request_id:
                role_request = self.db.query(RoleRequest).filter(
                    RoleRequest.id == role_request_id
                ).with_for_update().first()  # Lock for concurrency safety
                
                if role_request:
                    # Check if already approved (concurrency check)
                    if role_request.status == RoleRequestStatus.APPROVED:
                        logger.warning(
                            "role_request_already_approved",
                            role_request_id=role_request_id,
                            request_id=request_id
                        )
                        # Don't fail, just log - roles may have been granted already
                    else:
                        role_request.status = RoleRequestStatus.APPROVED
                        role_request.reviewed_by = granted_by
                        role_request.reviewed_at = datetime.utcnow()
            
            # Step 4: Audit log (before commit)
            actor_id = granted_by if granted_by else None
            action = "role_granted" if granted_by else "role_auto_granted"
            
            audit_service.log_action(
                db=self.db,
                action=action,
                actor_id=actor_id,
                target_type="user",
                target_id=user_id,
                meta={
                    "granted_roles": granted_roles,
                    "skipped_roles": skipped_roles,
                    "role_request_id": role_request_id
                },
                request_id=request_id
            )
            
            # Step 5: Commit entire transaction
            if profile_creation_failed:
                self.db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create required profiles for assigned roles"
                )
            
            self.db.commit()
            
            return {
                "granted_roles": granted_roles,
                "skipped_roles": skipped_roles
            }
            
        except HTTPException:
            # Re-raise HTTP exceptions
            self.db.rollback()
            raise
        except SQLAlchemyError as e:
            # Rollback on database errors
            self.db.rollback()
            logger.error(
                "role_grant_transaction_failed",
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
                request_id=request_id,
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to grant roles due to database error"
            )
        except Exception as e:
            # Rollback on any other unexpected errors
            self.db.rollback()
            logger.error(
                "role_grant_unexpected_error",
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
                request_id=request_id,
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while granting roles"
            )
    
    def reject_role_request(
        self,
        role_request_id: int,
        rejected_by: int,
        reason: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> RoleRequest:
        """
        Reject a role request with transactional safety.
        
        Args:
            role_request_id: ID of the role request
            rejected_by: Admin user ID who rejected the request
            reason: Optional rejection reason
            request_id: Optional request ID for correlation
            
        Returns:
            Updated RoleRequest object
            
        Raises:
            HTTPException: If role request not found
        """
        try:
            # Lock for concurrency safety
            role_request = self.db.query(RoleRequest).filter(
                RoleRequest.id == role_request_id
            ).with_for_update().first()
            
            if not role_request:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Role request not found"
                )
            
            # Check if already processed
            if role_request.status != RoleRequestStatus.PENDING:
                logger.warning(
                    "role_request_already_processed",
                    role_request_id=role_request_id,
                    current_status=role_request.status.value,
                    rejected_by=rejected_by,
                    request_id=request_id
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Role request is already {role_request.status.value}"
                )
            
            # Update status
            role_request.status = RoleRequestStatus.REJECTED
            role_request.reviewed_by = rejected_by
            role_request.reviewed_at = datetime.utcnow()
            role_request.notes = reason if reason else role_request.notes
            
            # Audit log
            audit_service.log_admin_action(
                db=self.db,
                action="role_request_rejected",
                admin_id=rejected_by,
                target_type="role_request",
                target_id=role_request_id,
                meta={
                    "requested_roles": role_request.requested_roles,
                    "reason": reason
                },
                request_id=request_id
            )
            
            # Commit transaction
            self.db.commit()
            self.db.refresh(role_request)
            
            # Send notification (non-blocking)
            try:
                user = self.db.query(User).filter(User.id == role_request.user_id).first()
                if user:
                    notification_service.send_role_rejection_notification(
                        to_email=user.email,
                        user_name=user.full_name or user.email,
                        rejected_roles=role_request.requested_roles,
                        reason=reason
                    )
            except Exception as e:
                logger.error(
                    "notification_send_failed",
                    role_request_id=role_request_id,
                    user_id=role_request.user_id,
                    error=str(e),
                    request_id=request_id,
                    exc_info=True
                )
            
            logger.info(
                "role_request_rejected",
                role_request_id=role_request_id,
                rejected_by=rejected_by,
                user_id=role_request.user_id
            )
            
            return role_request
            
        except HTTPException:
            self.db.rollback()
            raise
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(
                "role_request_rejection_failed",
                role_request_id=role_request_id,
                error=str(e),
                error_type=type(e).__name__,
                request_id=request_id,
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reject role request due to database error"
            )
    
    def approve_role_request(
        self,
        role_request_id: int,
        approved_by: int,
        request_id: Optional[str] = None
    ) -> RoleRequest:
        """
        Approve a role request and grant roles with concurrency safety.
        
        Enterprise-grade: Uses row-level locking to prevent duplicate approvals.
        
        Args:
            role_request_id: ID of the role request
            approved_by: Admin user ID who approved the request
            request_id: Optional request ID for correlation
            
        Returns:
            Updated RoleRequest object
            
        Raises:
            HTTPException: If role request not found or already processed
        """
        # Lock the role request for update to prevent concurrent approvals
        role_request = self.db.query(RoleRequest).filter(
            RoleRequest.id == role_request_id
        ).with_for_update().first()
        
        if not role_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role request not found"
            )
        
        # Check if already processed (concurrency safety)
        if role_request.status != RoleRequestStatus.PENDING:
            logger.warning(
                "role_request_already_processed",
                role_request_id=role_request_id,
                current_status=role_request.status.value,
                approved_by=approved_by,
                request_id=request_id
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Role request is already {role_request.status.value}"
            )
        
        # Grant roles (this handles transaction and profile creation)
        result = self.grant_roles(
            user_id=role_request.user_id,
            role_names=role_request.requested_roles,
            role_request_id=role_request_id,
            granted_by=approved_by,
            request_id=request_id
        )
        
        # Refresh role request to get updated status
        self.db.refresh(role_request)
        
        # Send notification (non-blocking - failures don't affect approval)
        if result["granted_roles"]:
            try:
                user = self.db.query(User).filter(User.id == role_request.user_id).first()
                if user:
                    notification_service.send_role_approval_notification(
                        to_email=user.email,
                        user_name=user.full_name or user.email,
                        approved_roles=result["granted_roles"]
                    )
            except Exception as e:
                # Log but don't fail - notification is non-critical
                logger.error(
                    "notification_send_failed",
                    role_request_id=role_request_id,
                    user_id=role_request.user_id,
                    error=str(e),
                    request_id=request_id,
                    exc_info=True
                )
        
        logger.info(
            "role_request_approved",
            role_request_id=role_request_id,
            approved_by=approved_by,
            user_id=role_request.user_id,
            granted_roles=result["granted_roles"]
        )
        
        return role_request

