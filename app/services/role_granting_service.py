"""
Role Granting Service for managing role assignments

Handles:
- Granting roles to users
- Updating role request status
- Sending notifications
- Integration with audit service
"""

from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from fastapi import HTTPException, status

from app.models.role_request import RoleRequest, RoleRequestStatus
from app.models.user_role import UserRole
from app.models.role import Role
from app.services.role_service import RoleService
from app.services.notification_service import notification_service
from app.services.audit_service import audit_service
from app.core.logger import get_logger

logger = get_logger(__name__)


class RoleGrantingService:
    """Service for role granting operations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.role_service = RoleService(db)
    
    def grant_roles(
        self,
        user_id: int,
        role_names: List[str],
        role_request_id: Optional[int] = None,
        granted_by: Optional[int] = None,
        request_id: Optional[str] = None
    ) -> dict:
        """
        Grant roles to a user
        
        Args:
            user_id: ID of the user to grant roles to
            role_names: List of role names to grant
            role_request_id: Optional associated role request ID
            granted_by: Optional admin user ID who granted the roles
            request_id: Optional request ID for correlation
            
        Returns:
            Dictionary with granted_roles and skipped_roles
            
        Raises:
            HTTPException: If validation fails
        """
        granted_roles = []
        skipped_roles = []
        
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
        
        # Update role request status if provided
        if role_request_id:
            role_request = self.db.query(RoleRequest).filter(
                RoleRequest.id == role_request_id
            ).first()
            
            if role_request:
                role_request.status = RoleRequestStatus.APPROVED
                role_request.reviewed_by = granted_by
                role_request.reviewed_at = datetime.utcnow()
                self.db.commit()
        
        # Audit log
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
        
        return {
            "granted_roles": granted_roles,
            "skipped_roles": skipped_roles
        }
    
    def reject_role_request(
        self,
        role_request_id: int,
        rejected_by: int,
        reason: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> RoleRequest:
        """
        Reject a role request
        
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
        role_request = self.db.query(RoleRequest).filter(
            RoleRequest.id == role_request_id
        ).first()
        
        if not role_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role request not found"
            )
        
        # Update status
        role_request.status = RoleRequestStatus.REJECTED
        role_request.reviewed_by = rejected_by
        role_request.reviewed_at = datetime.utcnow()
        role_request.notes = reason if reason else role_request.notes
        self.db.commit()
        self.db.refresh(role_request)
        
        # Get user email for notification
        from app.models.user import User
        user = self.db.query(User).filter(User.id == role_request.user_id).first()
        
        # Send notification
        if user:
            notification_service.send_role_rejection_notification(
                to_email=user.email,
                user_name=user.full_name or user.email,
                rejected_roles=role_request.requested_roles,
                reason=reason
            )
        
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
        
        logger.info(
            "role_request_rejected",
            role_request_id=role_request_id,
            rejected_by=rejected_by,
            user_id=role_request.user_id
        )
        
        return role_request
    
    def approve_role_request(
        self,
        role_request_id: int,
        approved_by: int,
        request_id: Optional[str] = None
    ) -> RoleRequest:
        """
        Approve a role request and grant roles
        
        Args:
            role_request_id: ID of the role request
            approved_by: Admin user ID who approved the request
            request_id: Optional request ID for correlation
            
        Returns:
            Updated RoleRequest object
            
        Raises:
            HTTPException: If role request not found
        """
        role_request = self.db.query(RoleRequest).filter(
            RoleRequest.id == role_request_id
        ).first()
        
        if not role_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role request not found"
            )
        
        # Grant roles
        result = self.grant_roles(
            user_id=role_request.user_id,
            role_names=role_request.requested_roles,
            role_request_id=role_request_id,
            granted_by=approved_by,
            request_id=request_id
        )
        
        # Get user email for notification
        from app.models.user import User
        user = self.db.query(User).filter(User.id == role_request.user_id).first()
        
        # Send notification
        if user and result["granted_roles"]:
            notification_service.send_role_approval_notification(
                to_email=user.email,
                user_name=user.full_name or user.email,
                approved_roles=result["granted_roles"]
            )
        
        # Refresh role request to get updated status
        self.db.refresh(role_request)
        
        logger.info(
            "role_request_approved",
            role_request_id=role_request_id,
            approved_by=approved_by,
            user_id=role_request.user_id,
            granted_roles=result["granted_roles"]
        )
        
        return role_request

