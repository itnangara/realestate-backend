"""
Audit Service for structured audit logging

Handles:
- Immutable audit trail to audit_logs table
- Request ID correlation
- Actor tracking (user, admin, or system)
- Structured JSON metadata
"""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from app.core.logger import get_logger

logger = get_logger(__name__)


class AuditService:
    """Audit service for structured logging to audit_logs table"""
    
    def log_action(
        self,
        db: Session,
        action: str,
        actor_id: Optional[int] = None,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> AuditLog:
        """
        Log an action to the audit_logs table
        
        Args:
            db: Database session
            action: Action name (e.g., "role_request_created", "role_granted")
            actor_id: User ID who performed the action (None for system actions)
            target_type: Type of target entity (e.g., "role_request", "kyc_request", "user")
            target_id: ID of the target entity
            meta: Additional structured metadata (JSON-serializable dict)
            request_id: HTTP request ID for correlation
        
        Returns:
            Created AuditLog record
        """
        try:
            audit_log = AuditLog(
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                meta=meta,
                request_id=request_id
            )
            
            db.add(audit_log)
            db.commit()
            db.refresh(audit_log)
            
            logger.info(
                "audit_log_created",
                audit_log_id=audit_log.id,
                action=action,
                actor_id=actor_id,
                target_type=target_type,
                target_id=target_id,
                request_id=request_id
            )
            
            return audit_log
            
        except Exception as e:
            logger.error(
                "failed_to_create_audit_log",
                error=str(e),
                action=action,
                actor_id=actor_id,
                target_type=target_type,
                target_id=target_id
            )
            db.rollback()
            raise
    
    def log_user_action(
        self,
        db: Session,
        action: str,
        user_id: int,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> AuditLog:
        """
        Log an action performed by a user
        
        Args:
            db: Database session
            action: Action name
            user_id: User ID who performed the action
            target_type: Type of target entity
            target_id: ID of the target entity
            meta: Additional metadata
            request_id: HTTP request ID
        
        Returns:
            Created AuditLog record
        """
        return self.log_action(
            db=db,
            action=action,
            actor_id=user_id,
            target_type=target_type,
            target_id=target_id,
            meta=meta,
            request_id=request_id
        )
    
    def log_admin_action(
        self,
        db: Session,
        action: str,
        admin_id: int,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> AuditLog:
        """
        Log an action performed by an admin
        
        Args:
            db: Database session
            action: Action name
            admin_id: Admin user ID who performed the action
            target_type: Type of target entity
            target_id: ID of the target entity
            meta: Additional metadata
            request_id: HTTP request ID
        
        Returns:
            Created AuditLog record
        """
        return self.log_action(
            db=db,
            action=action,
            actor_id=admin_id,
            target_type=target_type,
            target_id=target_id,
            meta=meta,
            request_id=request_id
        )
    
    def log_system_action(
        self,
        db: Session,
        action: str,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> AuditLog:
        """
        Log a system action (no actor)
        
        Args:
            db: Database session
            action: Action name
            target_type: Type of target entity
            target_id: ID of the target entity
            meta: Additional metadata
            request_id: HTTP request ID
        
        Returns:
            Created AuditLog record
        """
        return self.log_action(
            db=db,
            action=action,
            actor_id=None,  # System action has no actor
            target_type=target_type,
            target_id=target_id,
            meta=meta,
            request_id=request_id
        )


# Singleton instance
audit_service = AuditService()

