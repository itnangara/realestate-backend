"""
Webhook routes for external service callbacks

Endpoints:
- POST /api/webhooks/kyc - KYC provider webhook
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import json

from app.utils.database import get_db
from app.services.kyc_service import KYCService, MockKYCProvider
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


def get_kyc_service(db: Session = Depends(get_db)) -> KYCService:
    """Dependency to get KYC service instance"""
    from app.services.kyc_provider_factory import get_kyc_provider
    provider = get_kyc_provider()  # Uses configured provider from environment
    return KYCService(db, provider)


@router.post(
    "/kyc",
    status_code=status.HTTP_200_OK,
    summary="KYC provider webhook",
    response_description="Webhook processed successfully"
)
async def kyc_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    x_provider: Optional[str] = Header(None, alias="X-Provider")
):
    """
    Handle webhook from KYC provider.
    
    This endpoint:
    - Verifies webhook signature for security
    - Processes webhook payload with idempotency
    - Updates KYC request status
    - Triggers evaluate_kyc_verdict task
    - Logs all webhook events in audit trail
    
    The webhook should include:
    - provider_reference: Provider's reference ID
    - verdict: Provider's verdict data
    - Additional provider-specific data
    """
    request_id = getattr(request.state, 'request_id', None)
    
    # Read raw payload for signature verification
    body = await request.body()
    
    # Parse JSON payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    # Extract webhook data
    provider_reference = payload.get("provider_reference") or payload.get("reference_id")
    verdict = payload.get("verdict") or payload.get("result")
    
    if not provider_reference:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing provider_reference in webhook payload"
        )
    
    if not verdict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing verdict in webhook payload"
        )
    
    # Get KYC service with provider
    kyc_service = get_kyc_service(db)
    
    # Verify webhook signature (if provided)
    if x_signature:
        headers = dict(request.headers)
        is_valid = kyc_service.provider.verify_webhook_signature(
            payload=body,
            signature=x_signature,
            headers=headers
        )
        
        if not is_valid:
            logger.warning(
                "kyc_webhook_signature_invalid",
                provider_reference=provider_reference,
                request_id=request_id
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
            )
    
    # Process webhook with idempotency
    try:
        kyc_request = await kyc_service.process_webhook(
            provider_reference=provider_reference,
            verdict=verdict if isinstance(verdict, dict) else {"result": verdict},
            raw_response=payload,
            request_id=request_id
        )
        
        logger.info(
            "kyc_webhook_processed_successfully",
            kyc_request_id=kyc_request.id,
            provider_reference=provider_reference,
            status=kyc_request.status.value
        )
        
        return {
            "status": "success",
            "kyc_request_id": kyc_request.id,
            "provider_reference": provider_reference,
            "verdict_status": kyc_request.status.value
        }
        
    except ValueError as e:
        logger.error(
            "kyc_webhook_processing_failed",
            error=str(e),
            provider_reference=provider_reference,
            request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "kyc_webhook_unexpected_error",
            error=str(e),
            provider_reference=provider_reference,
            request_id=request_id,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook"
        )

