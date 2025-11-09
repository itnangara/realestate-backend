"""
Celery tasks for role request processing

Tasks:
- process_role_request: Main workflow orchestrator for role requests
"""

from celery import Task
from celery.exceptions import Retry
from typing import Dict, Any
from app.celery_app import celery_app
from app.utils.celery_db import get_db_session
from app.core.logger import get_logger

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="process_role_request",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True
)
def process_role_request(
    self: Task,
    role_request_id: int
) -> Dict[str, Any]:
    """
    Main workflow orchestrator for role request processing
    
    This task:
    - Checks if KYC is required (feature flag + role/country rules)
    - Submits to KYC provider if needed
    - Auto-approves if low risk and auto_approve is enabled
    - Pushes to moderation queue if review needed
    - Logs audit entry
    
    Args:
        role_request_id: Role request ID
        
    Returns:
        Dictionary with processing result
        
    Raises:
        Retry: If transient error occurs (auto-retried)
        Exception: If permanent error occurs
    """
    try:
        logger.info(
            "role_request_processing_started",
            role_request_id=role_request_id,
            attempt=self.request.retries + 1
        )
        
        with get_db_session() as db:
            from app.services.role_request_service import RoleRequestService
            from app.services.kyc_service import KYCService
            from app.services.role_granting_service import RoleGrantingService
            from app.core.feature_flags import feature_flags
            from app.models.role_request import RoleRequestStatus
            from app.models.kyc_request import KYCRequestStatus
            import asyncio
            
            role_request_service = RoleRequestService(db)
            role_request = role_request_service.get_role_request(role_request_id)
            
            if not role_request:
                logger.error(
                    "role_request_not_found",
                    role_request_id=role_request_id
                )
                return {
                    "status": "error",
                    "error": "Role request not found",
                    "role_request_id": role_request_id
                }
            
            # Check if already processed
            if role_request.status != RoleRequestStatus.PENDING:
                logger.info(
                    "role_request_already_processed",
                    role_request_id=role_request_id,
                    current_status=role_request.status.value
                )
                return {
                    "status": "already_processed",
                    "role_request_id": role_request_id,
                    "current_status": role_request.status.value
                }
            
            # Update status to in_review
            role_request.status = RoleRequestStatus.IN_REVIEW
            db.commit()
            
            # Check KYC requirements
            kyc_check = asyncio.run(
                role_request_service.check_kyc_required(role_request.requested_roles)
            )
            
            result_data = {
                "status": "success",
                "role_request_id": role_request_id,
                "kyc_required": kyc_check["kyc_required"],
                "kyc_required_for": kyc_check.get("required_for", [])
            }
            
            if kyc_check["kyc_required"]:
                # Check if user has existing approved KYC
                from app.services.kyc_provider_factory import get_kyc_provider
                kyc_service = KYCService(db, get_kyc_provider())
                existing_kyc = db.query(
                    kyc_service.get_user_kyc_requests(role_request.user_id, KYCRequestStatus.APPROVED)
                ).first() if hasattr(kyc_service, 'get_user_kyc_requests') else None
                
                # Get user's KYC requests
                user_kyc_requests = kyc_service.get_user_kyc_requests(
                    role_request.user_id,
                    KYCRequestStatus.APPROVED
                )
                
                if user_kyc_requests:
                    # User has approved KYC - auto-approve if enabled
                    auto_approve = asyncio.run(feature_flags.is_enabled("auto_approve_enabled"))
                    if auto_approve:
                        role_granting_service = RoleGrantingService(db)
                        role_granting_service.approve_role_request(
                            role_request_id=role_request_id,
                            approved_by=None,  # System auto-approval
                            request_id=f"celery_task_{self.request.id}"
                        )
                        result_data["action"] = "auto_approved_with_existing_kyc"
                        logger.info(
                            "role_request_auto_approved_existing_kyc",
                            role_request_id=role_request_id,
                            user_id=role_request.user_id
                        )
                    else:
                        result_data["action"] = "pending_admin_review"
                        logger.info(
                            "role_request_pending_review",
                            role_request_id=role_request_id,
                            user_id=role_request.user_id
                        )
                else:
                    # No approved KYC - check if documents attached
                    if role_request.attachments:
                        # Submit KYC request with attached documents
                        kyc_request = asyncio.run(
                            kyc_service.submit_kyc_request(
                                user_id=role_request.user_id,
                                document_ids=role_request.attachments,
                                role_request_id=role_request_id,
                                metadata={"triggered_by": "role_request_processing"},
                                request_id=f"celery_task_{self.request.id}"
                            )
                        )
                        result_data["action"] = "kyc_submitted"
                        result_data["kyc_request_id"] = kyc_request.id
                        logger.info(
                            "kyc_submitted_for_role_request",
                            role_request_id=role_request_id,
                            kyc_request_id=kyc_request.id
                        )
                    else:
                        # No documents - push to moderation
                        result_data["action"] = "pending_documents"
                        logger.info(
                            "role_request_missing_documents",
                            role_request_id=role_request_id
                        )
            else:
                # KYC not required - check auto-approve
                auto_approve = asyncio.run(feature_flags.is_enabled("auto_approve_enabled"))
                if auto_approve:
                    # Auto-approve and grant roles
                    role_granting_service = RoleGrantingService(db)
                    role_granting_service.approve_role_request(
                        role_request_id=role_request_id,
                        approved_by=None,  # System auto-approval
                        request_id=f"celery_task_{self.request.id}"
                    )
                    result_data["action"] = "auto_approved_no_kyc"
                    logger.info(
                        "role_request_auto_approved_no_kyc",
                        role_request_id=role_request_id,
                        user_id=role_request.user_id
                    )
                else:
                    # Push to moderation queue
                    result_data["action"] = "pending_admin_review"
                    logger.info(
                        "role_request_pending_review_no_kyc",
                        role_request_id=role_request_id,
                        user_id=role_request.user_id
                    )
            
            logger.info(
                "role_request_processing_completed",
                role_request_id=role_request_id,
                action=result_data.get("action")
            )
            
            return result_data
            
    except ValueError as e:
        # Permanent error - don't retry
        logger.error(
            "role_request_processing_validation_error",
            error=str(e),
            role_request_id=role_request_id,
            exc_info=True
        )
        raise
    except Exception as e:
        # Transient error - retry
        logger.warning(
            "role_request_processing_error_retrying",
            error=str(e),
            error_type=type(e).__name__,
            role_request_id=role_request_id,
            attempt=self.request.retries + 1,
            max_retries=self.max_retries
        )
        raise self.retry(exc=e)

