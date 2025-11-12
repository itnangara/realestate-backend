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
from datetime import datetime
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
            Created or merged RoleRequest object
            
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
        new_attachments = None
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
            new_attachments = [str(doc.file_id) for doc in documents]
        
        # Step 1: Check for existing pending request with row-level locking
        # Use with_for_update() to prevent race conditions in concurrent scenarios
        existing_request = self.db.query(RoleRequest).filter(
            RoleRequest.user_id == user_id,
            RoleRequest.status == RoleRequestStatus.PENDING
        ).with_for_update().first()
        
        if existing_request:
            # Step 2: Merge into existing pending request
            existing_roles = set(existing_request.requested_roles or [])
            new_roles_set = set(requested_roles)
            
            # Find overlapping and new roles
            overlapping_roles = existing_roles.intersection(new_roles_set)
            new_roles_to_add = list(new_roles_set - existing_roles)
            
            # Merge roles (only add non-overlapping ones)
            if new_roles_to_add:
                existing_request.requested_roles = list(existing_roles) + new_roles_to_add
                roles_merged = True
            else:
                roles_merged = False
            
            # Merge attachments (deduplicate using set operations)
            # Defensive: Ensure attachments is always a list (JSONBType can return list or dict)
            existing_attachments_raw = existing_request.attachments or []
            if not isinstance(existing_attachments_raw, list):
                existing_attachments_raw = []
            existing_attachments = set(existing_attachments_raw)
            new_attachments_set = set(new_attachments or [])
            
            # Find new attachments to add
            new_attachments_to_add = list(new_attachments_set - existing_attachments)
            
            if new_attachments_to_add:
                existing_request.attachments = list(existing_attachments) + new_attachments_to_add
                attachments_merged = True
            else:
                attachments_merged = False
            
            # Merge notes (append with separator)
            if notes:
                if existing_request.notes:
                    existing_request.notes = f"{existing_request.notes}\n\n---\n\n{notes}"
                else:
                    existing_request.notes = notes
                notes_merged = True
            else:
                notes_merged = False
            
            # Commit merge changes atomically
            self.db.commit()
            self.db.refresh(existing_request)
            
            # Audit log for merge operation
            merge_meta = {
                "existing_request_id": existing_request.id,
                "new_roles_submitted": requested_roles,
                "overlapping_roles": list(overlapping_roles),
                "roles_added": new_roles_to_add if roles_merged else [],
                "attachments_added": new_attachments_to_add if attachments_merged else [],
                "notes_appended": notes_merged
            }
            if document_ids:
                merge_meta["document_ids"] = [str(doc_id) for doc_id in document_ids]
            
            audit_service.log_user_action(
                db=self.db,
                action="role_request_merged",
                user_id=user_id,
                target_type="role_request",
                target_id=existing_request.id,
                meta=merge_meta,
                request_id=request_id
            )
            
            logger.info(
                "role_request_merged",
                role_request_id=existing_request.id,
                user_id=user_id,
                existing_roles=list(existing_roles),
                new_roles_added=new_roles_to_add,
                overlapping_roles=list(overlapping_roles),
                attachments_added=new_attachments_to_add
            )
            
            # Enqueue async job only if new roles were added (avoid duplicate processing)
            if roles_merged:
                try:
                    from app.tasks.role_tasks import process_role_request
                    process_role_request.delay(existing_request.id)
                    logger.info(
                        "role_request_processing_queued",
                        role_request_id=existing_request.id
                    )
                except ImportError:
                    logger.debug(
                        "celery_not_available",
                        role_request_id=existing_request.id
                    )
                except Exception as e:
                    logger.warning(
                        "failed_to_enqueue_role_request",
                        role_request_id=existing_request.id,
                        error=str(e)
                    )
            
            return existing_request
        
        # Step 3: No existing pending request - create new one
        role_request = RoleRequest(
            user_id=user_id,
            requested_roles=requested_roles,
            status=RoleRequestStatus.PENDING,
            attachments=new_attachments,
            notes=notes
        )
        
        self.db.add(role_request)
        self.db.commit()
        self.db.refresh(role_request)
        
        # Audit log for new request creation
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
    
    def get_role_request_with_documents(
        self,
        role_request_id: int
    ) -> Optional[RoleRequest]:
        """
        Get role request by ID with documents for admin access
        
        Args:
            role_request_id: ID of the role request
            
        Returns:
            RoleRequest object or None if not found
        """
        role_request = self.db.query(RoleRequest).filter(
            RoleRequest.id == role_request_id
        ).first()
        
        return role_request
    
    def get_role_requests_with_documents(
        self,
        status_filter: Optional[RoleRequestStatus] = None,
        user_id_filter: Optional[int] = None,
        role_filter: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[RoleRequest]:
        """
        Get role requests with filters for admin access
        
        Args:
            status_filter: Optional filter by status
            user_id_filter: Optional filter by user ID
            role_filter: Optional filter by requested role name
            date_from: Optional filter by date from
            date_to: Optional filter by date to
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of RoleRequest objects
        """
        query = self.db.query(RoleRequest)
        
        if status_filter:
            query = query.filter(RoleRequest.status == status_filter)
        
        if user_id_filter:
            query = query.filter(RoleRequest.user_id == user_id_filter)
        
        if role_filter:
            # Filter by role in requested_roles array
            # For PostgreSQL ARRAY, use contains; for SQLite JSON, filter in Python
            query = query.filter(RoleRequest.requested_roles.contains([role_filter]))
        
        if date_from:
            query = query.filter(RoleRequest.requested_at >= date_from)
        
        if date_to:
            query = query.filter(RoleRequest.requested_at <= date_to)
        
        results = query.order_by(RoleRequest.requested_at.desc()).offset(offset).limit(limit).all()
        return results if results is not None else []
    
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

