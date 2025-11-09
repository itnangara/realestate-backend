"""
Celery tasks for KYC processing

Tasks:
- submit_kyc_request: Submit KYC verification to provider
- evaluate_kyc_verdict: Process KYC provider response and update role requests
"""

from celery import Task
from celery.exceptions import Retry
from typing import List, Dict, Any, Optional
from app.celery_app import celery_app
from app.utils.celery_db import get_db_session
from app.services.kyc_service import KYCService
from app.core.logger import get_logger

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="submit_kyc_request",
    max_retries=3,
    default_retry_delay=60,  # 1 minute
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,  # 10 minutes max
    retry_jitter=True
)
def submit_kyc_request(
    self: Task,
    user_id: int,
    document_ids: List[int],
    role_request_id: int,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Submit KYC verification request to provider
    
    This task:
    - Creates KYC request record
    - Submits to KYC provider
    - Stores provider reference for idempotency
    - Logs audit entry
    
    Args:
        user_id: User ID
        document_ids: List of document IDs
        role_request_id: Associated role request ID
        metadata: Additional metadata
        
    Returns:
        Dictionary with kyc_request_id and provider_reference
        
    Raises:
        Retry: If transient error occurs (auto-retried)
        Exception: If permanent error occurs
    """
    try:
        logger.info(
            "kyc_task_started",
            user_id=user_id,
            role_request_id=role_request_id,
            document_ids=document_ids,
            attempt=self.request.retries + 1
        )
        
        with get_db_session() as db:
            # Initialize KYC service with configured provider
            from app.services.kyc_provider_factory import get_kyc_provider
            kyc_service = KYCService(db, get_kyc_provider())
            
            # Submit KYC request (service handles idempotency)
            # Note: submit_kyc_request is async, but Celery tasks are sync
            # We need to run it in an event loop
            import asyncio
            kyc_request = asyncio.run(
                kyc_service.submit_kyc_request(
                    user_id=user_id,
                    document_ids=document_ids,
                    role_request_id=role_request_id,
                    metadata=metadata or {},
                    request_id=f"celery_task_{self.request.id}"
                )
            )
            
            logger.info(
                "kyc_task_completed",
                kyc_request_id=kyc_request.id,
                provider_reference=kyc_request.provider_reference,
                user_id=user_id,
                role_request_id=role_request_id
            )
            
            return {
                "status": "success",
                "kyc_request_id": kyc_request.id,
                "provider_reference": kyc_request.provider_reference,
                "status_value": kyc_request.status.value
            }
            
    except ValueError as e:
        # Permanent error - don't retry
        logger.error(
            "kyc_task_validation_error",
            error=str(e),
            user_id=user_id,
            role_request_id=role_request_id,
            exc_info=True
        )
        raise
    except Exception as e:
        # Transient error - retry
        logger.warning(
            "kyc_task_error_retrying",
            error=str(e),
            error_type=type(e).__name__,
            user_id=user_id,
            role_request_id=role_request_id,
            attempt=self.request.retries + 1,
            max_retries=self.max_retries
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    name="evaluate_kyc_verdict",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True
)
def evaluate_kyc_verdict(
    self: Task,
    kyc_request_id: int,
    verdict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Evaluate KYC provider verdict and update role requests
    
    This task:
    - Updates KYC request status
    - Auto-approves role requests if verdict is approved and auto_approve is enabled
    - Pushes to moderation queue if review needed
    - Triggers role granting if applicable
    - Logs audit entry
    
    Args:
        kyc_request_id: KYC request ID
        verdict: Provider verdict data
        
    Returns:
        Dictionary with evaluation result
        
    Raises:
        Retry: If transient error occurs (auto-retried)
        Exception: If permanent error occurs
    """
    try:
        logger.info(
            "kyc_verdict_evaluation_started",
            kyc_request_id=kyc_request_id,
            verdict_result=verdict.get("result"),
            attempt=self.request.retries + 1
        )
        
        with get_db_session() as db:
            from app.services.kyc_service import KYCService
            from app.services.role_granting_service import RoleGrantingService
            from app.services.role_request_service import RoleRequestService
            from app.core.feature_flags import feature_flags
            from app.models.kyc_request import KYCRequestStatus
            from app.models.role_request import RoleRequestStatus
            import asyncio
            
            kyc_service = KYCService(db)
            kyc_request = kyc_service.get_kyc_request(kyc_request_id)
            
            if not kyc_request:
                logger.error(
                    "kyc_request_not_found",
                    kyc_request_id=kyc_request_id
                )
                return {
                    "status": "error",
                    "error": "KYC request not found",
                    "kyc_request_id": kyc_request_id
                }
            
            # Check if already processed (idempotency)
            if kyc_request.status in [KYCRequestStatus.APPROVED, KYCRequestStatus.REJECTED]:
                logger.info(
                    "kyc_verdict_already_processed",
                    kyc_request_id=kyc_request_id,
                    current_status=kyc_request.status.value
                )
                return {
                    "status": "already_processed",
                    "kyc_request_id": kyc_request_id,
                    "current_status": kyc_request.status.value
                }
            
            # Update KYC request with verdict (if not already updated by webhook)
            if not kyc_request.verdict:
                from datetime import datetime
                kyc_request.verdict = verdict
                kyc_request.completed_at = datetime.utcnow()
                
                # Determine status from verdict
                result = verdict.get("result", "").lower()
                if result == "approved":
                    kyc_request.status = KYCRequestStatus.APPROVED
                elif result == "rejected":
                    kyc_request.status = KYCRequestStatus.REJECTED
                else:
                    kyc_request.status = KYCRequestStatus.IN_REVIEW
                
                db.commit()
            
            # Check if auto-approve is enabled
            auto_approve = asyncio.run(feature_flags.is_enabled("auto_approve_enabled"))
            
            result_data = {
                "status": "success",
                "kyc_request_id": kyc_request_id,
                "kyc_status": kyc_request.status.value,
                "verdict_result": verdict.get("result"),
                "auto_approve_enabled": auto_approve
            }
            
            # Auto-approve role requests if KYC approved and auto_approve enabled
            if auto_approve and kyc_request.status == KYCRequestStatus.APPROVED:
                # Find associated role requests
                role_request_service = RoleRequestService(db)
                
                # Get role requests for this user that are pending and require KYC
                from app.models.role_request import RoleRequest
                pending_requests = db.query(RoleRequest).filter(
                    RoleRequest.user_id == kyc_request.user_id,
                    RoleRequest.status == RoleRequestStatus.PENDING
                ).all()
                
                role_granting_service = RoleGrantingService(db)
                approved_count = 0
                
                for role_request in pending_requests:
                    # Check if this role request requires KYC for its roles
                    kyc_check = asyncio.run(
                        role_request_service.check_kyc_required(role_request.requested_roles)
                    )
                    
                    if kyc_check["kyc_required"]:
                        # Auto-approve and grant roles
                        try:
                            role_granting_service.approve_role_request(
                                role_request_id=role_request.id,
                                approved_by=None,  # System auto-approval
                                request_id=f"celery_task_{self.request.id}"
                            )
                            approved_count += 1
                            logger.info(
                                "role_request_auto_approved",
                                role_request_id=role_request.id,
                                user_id=kyc_request.user_id,
                                kyc_request_id=kyc_request_id
                            )
                        except Exception as e:
                            logger.error(
                                "role_request_auto_approval_failed",
                                role_request_id=role_request.id,
                                error=str(e),
                                exc_info=True
                            )
                
                result_data["auto_approved_requests"] = approved_count
            
            logger.info(
                "kyc_verdict_evaluation_completed",
                kyc_request_id=kyc_request_id,
                verdict_result=verdict.get("result"),
                auto_approved_requests=result_data.get("auto_approved_requests", 0)
            )
            
            return result_data
            
    except ValueError as e:
        # Permanent error - don't retry
        logger.error(
            "kyc_verdict_evaluation_validation_error",
            error=str(e),
            kyc_request_id=kyc_request_id,
            exc_info=True
        )
        raise
    except Exception as e:
        # Transient error - retry
        logger.warning(
            "kyc_verdict_evaluation_error_retrying",
            error=str(e),
            error_type=type(e).__name__,
            kyc_request_id=kyc_request_id,
            attempt=self.request.retries + 1,
            max_retries=self.max_retries
        )
        raise self.retry(exc=e)

