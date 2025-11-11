"""
Role Request Service for managing role requests

Handles:
- Role request creation with document attachments
- Status tracking and workflow
- Integration with audit service and feature flags
- KYC requirement checking
"""

from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import HTTPException, status

from app.models.role_request import RoleRequest, RoleRequestStatus
from app.models.document import Document
from app.services.audit_service import audit_service
from app.services.document_service import DocumentService
from app.core.feature_flags import feature_flags
from app.core.logger import get_logger

logger = get_logger(__name__)


class RoleRequestService:
    """Service for role request management operations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.document_service = DocumentService(db)
    
    async def create_role_request(
        self,
        user_id: int,
        requested_roles: List[str],
        document_ids: Optional[List] = None,
        notes: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> RoleRequest:
        """
        Create a new role request or merge into existing pending request.
    

        Args:
            user_id: ID of the user making the request
            requested_roles: List of role names to request
            document_ids: Optional list of document file UUIDs to attach
            notes: Optional notes for the request
            request_id: Optional request ID for correlation
            
        Returns:
            Created RoleRequest object
            
        Raises:
            HTTPException: If feature flag is disabled or validation fails
        """
        # Check feature flag
        is_enabled = await feature_flags.is_enabled("role_request_enabled")
        if not is_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Role requests are currently disabled"
            )
        
        # Validate documents if provided (document_ids are UUIDs)
        attachments = None
        if document_ids:
            # Convert UUID strings to list for query
            file_id_strings = [str(doc_id) for doc_id in document_ids]
            documents = self.document_service.get_documents_by_file_ids(file_id_strings, user_id)
            
            if len(documents) != len(document_ids):
                found_file_ids = {str(doc.file_id) for doc in documents}
                requested_file_ids = {str(doc_id) for doc_id in document_ids}
                missing_ids = requested_file_ids - found_file_ids
                logger.warning(
                    "role_request_documents_not_found",
                    user_id=user_id,
                    missing_document_ids=list(missing_ids)
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Documents not found or do not belong to you: {list(missing_ids)}"
                )
            
            # Store document file UUIDs as JSON array (for external API exposure)
            attachments = [str(doc.file_id) for doc in documents]
        
        # Create role request
        role_request = RoleRequest(
            user_id=user_id,
            requested_roles=requested_roles,
            status=RoleRequestStatus.PENDING,
            attachments=attachments,
            notes=notes
        )
        
        self.db.add(role_request)
        self.db.commit()
        self.db.refresh(role_request)
        
        # Audit log - convert UUID objects to strings for JSON serialization
        meta = {
            "requested_roles": requested_roles,
            "notes": notes
        }
        if document_ids:
            meta["document_ids"] = [str(doc_id) for doc_id in document_ids]
        
        audit_service.log_user_action(
            db=self.db,
            action="role_request_created",
            user_id=user_id,
            target_type="role_request",
            target_id=role_request.id,
            meta=meta,
            request_id=request_id
        )
        
        logger.info(
            "role_request_created",
            role_request_id=role_request.id,
            user_id=user_id,
            requested_roles=requested_roles
        )
        
        # Enqueue async job for role processing (if celery available)
        try:
            from app.tasks.role_tasks import process_role_request
            process_role_request.delay(role_request.id)
            logger.info(
                "role_request_processing_queued",
                role_request_id=role_request.id
            )
        except ImportError:
            logger.debug(
                "celery_not_available",
                role_request_id=role_request.id
            )
        except Exception as e:
            logger.warning(
                "failed_to_enqueue_role_request",
                role_request_id=role_request.id,
                error=str(e)
            )
        
        return role_request
    
    def get_user_role_requests(
        self,
        user_id: int,
        status_filter: Optional[RoleRequestStatus] = None
    ) -> List[RoleRequest]:
        """
        Get all role requests for a user.
        
        Enterprise-grade: Always returns a list, never None.
        Returns empty list [] if no requests found.
        
        Args:
            user_id: ID of the user
            status_filter: Optional filter by status
            
        Returns:
            List of RoleRequest objects (empty list if none found)
        """
        query = self.db.query(RoleRequest).filter(RoleRequest.user_id == user_id)
        
        if status_filter:
            query = query.filter(RoleRequest.status == status_filter)
        
        results = query.order_by(RoleRequest.requested_at.desc()).all()
        # Defensive: Ensure we always return a list, never None
        return results if results is not None else []
    
    def get_role_request(
        self,
        role_request_id: int,
        user_id: Optional[int] = None
    ) -> Optional[RoleRequest]:
        """
        Get role request by ID with optional authorization check
        
        Args:
            role_request_id: ID of the role request
            user_id: Optional user ID for authorization (if provided, only returns if user owns it)
            
        Returns:
            RoleRequest object or None if not found/unauthorized
        """
        query = self.db.query(RoleRequest).filter(RoleRequest.id == role_request_id)
        
        if user_id:
            query = query.filter(RoleRequest.user_id == user_id)
        
        return query.first()
    
    async def check_kyc_required(
        self,
        requested_roles: List[str]
    ) -> dict:
        """
        Check if KYC is required for the requested roles
        
        Args:
            requested_roles: List of role names
            
        Returns:
            Dictionary with kyc_required flag and required_for list
        """
        kyc_required = False
        required_for = []
        
        for role in requested_roles:
            flag_name = f"kyc_required_for_{role}"
            is_required = await feature_flags.is_enabled(flag_name)
            if is_required:
                kyc_required = True
                required_for.append(role)
        
        return {
            "kyc_required": kyc_required,
            "required_for": required_for
        }

