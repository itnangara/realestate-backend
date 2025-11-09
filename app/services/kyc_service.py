"""
KYC Service for Know Your Customer verification

Handles:
- Abstract provider interface (mock, Sumsub, etc.)
- KYC request submission
- Webhook processing with idempotency
- Integration with role requests
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from app.models.kyc_request import KYCRequest, KYCRequestStatus
from app.models.document import Document
from app.services.audit_service import audit_service
from app.core.logger import get_logger

logger = get_logger(__name__)


class KYCProvider(ABC):
    """Abstract base class for KYC providers"""
    
    @abstractmethod
    async def submit_verification(
        self,
        user_id: int,
        document_ids: List[int],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit KYC verification request to provider
        
        Args:
            user_id: User ID
            document_ids: List of document IDs to verify
            metadata: Additional metadata
            
        Returns:
            Dictionary with provider_reference and any provider-specific data
        """
        pass
    
    @abstractmethod
    async def get_verification_status(
        self,
        provider_reference: str
    ) -> Dict[str, Any]:
        """
        Get verification status from provider
        
        Args:
            provider_reference: Provider's reference ID
            
        Returns:
            Dictionary with status and verdict
        """
        pass
    
    @abstractmethod
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        headers: Dict[str, str]
    ) -> bool:
        """
        Verify webhook signature for security
        
        Args:
            payload: Raw webhook payload
            signature: Signature from headers
            headers: Webhook headers
            
        Returns:
            True if signature is valid
        """
        pass


class MockKYCProvider(KYCProvider):
    """Mock KYC provider for development and testing"""
    
    def __init__(self):
        self.verifications: Dict[str, Dict[str, Any]] = {}
    
    async def submit_verification(
        self,
        user_id: int,
        document_ids: List[int],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Submit verification to mock provider"""
        provider_reference = f"mock_{uuid.uuid4().hex[:16]}"
        
        # Mock provider immediately returns a reference
        # In real implementation, this would call the provider API
        self.verifications[provider_reference] = {
            "user_id": user_id,
            "document_ids": document_ids,
            "status": "submitted",
            "submitted_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        
        logger.info(
            "kyc_verification_submitted",
            provider="mock",
            provider_reference=provider_reference,
            user_id=user_id
        )
        
        return {
            "provider_reference": provider_reference,
            "status": "submitted"
        }
    
    async def get_verification_status(
        self,
        provider_reference: str
    ) -> Dict[str, Any]:
        """Get verification status from mock provider"""
        verification = self.verifications.get(provider_reference)
        
        if not verification:
            return {
                "status": "not_found",
                "verdict": None
            }
        
        # Mock provider: auto-approve after "processing"
        # In real implementation, this would poll the provider API
        return {
            "status": verification.get("status", "submitted"),
            "verdict": {
                "result": "approved",
                "confidence": 0.95,
                "checks": {
                    "identity": "passed",
                    "document": "passed",
                    "liveness": "passed"
                }
            }
        }
    
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        headers: Dict[str, str]
    ) -> bool:
        """Mock webhook signature verification (always returns True for development)"""
        # In production, implement proper signature verification
        logger.warning(
            "mock_webhook_signature_verification",
            message="Using mock provider - signature verification bypassed"
        )
        return True


class KYCService:
    """Service for KYC verification operations"""
    
    def __init__(self, db: Session, provider: Optional[KYCProvider] = None):
        self.db = db
        self.provider = provider or MockKYCProvider()
    
    async def submit_kyc_request(
        self,
        user_id: int,
        document_ids: List[int],
        role_request_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> KYCRequest:
        """
        Submit a KYC verification request
        
        Args:
            user_id: User ID
            document_ids: List of document IDs to verify
            role_request_id: Optional associated role request ID
            metadata: Additional metadata
            request_id: Optional request ID for correlation
            
        Returns:
            Created KYCRequest object
            
        Raises:
            HTTPException: If validation fails
        """
        # Check for existing KYC request for this user (idempotency)
        existing_request = self.db.query(KYCRequest).filter(
            KYCRequest.user_id == user_id,
            KYCRequest.status.in_([
                KYCRequestStatus.SUBMITTED,
                KYCRequestStatus.IN_REVIEW
            ])
        ).first()
        
        if existing_request:
            logger.info(
                "kyc_request_already_exists",
                kyc_request_id=existing_request.id,
                user_id=user_id,
                status=existing_request.status.value
            )
            return existing_request
        
        # Verify documents belong to user
        documents = self.db.query(Document).filter(
            Document.id.in_(document_ids),
            Document.user_id == user_id
        ).all()
        
        if len(documents) != len(document_ids):
            raise ValueError("One or more documents not found or do not belong to user")
        
        # Submit to provider
        provider_result = await self.provider.submit_verification(
            user_id=user_id,
            document_ids=document_ids,
            metadata=metadata
        )
        
        provider_reference = provider_result.get("provider_reference")
        if not provider_reference:
            raise ValueError("Provider did not return a reference ID")
        
        # Check for duplicate provider_reference (idempotency)
        existing_by_ref = self.db.query(KYCRequest).filter(
            KYCRequest.provider_reference == provider_reference
        ).first()
        
        if existing_by_ref:
            logger.warning(
                "duplicate_provider_reference",
                provider_reference=provider_reference,
                existing_kyc_request_id=existing_by_ref.id
            )
            return existing_by_ref
        
        # Create KYC request
        kyc_request = KYCRequest(
            user_id=user_id,
            provider_reference=provider_reference,
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        
        self.db.add(kyc_request)
        self.db.commit()
        self.db.refresh(kyc_request)
        
        # Audit log
        audit_service.log_system_action(
            db=self.db,
            action="kyc_request_submitted",
            target_type="kyc_request",
            target_id=kyc_request.id,
            meta={
                "user_id": user_id,
                "provider_reference": provider_reference,
                "document_ids": document_ids,
                "role_request_id": role_request_id,
                "metadata": metadata
            },
            request_id=request_id
        )
        
        logger.info(
            "kyc_request_created",
            kyc_request_id=kyc_request.id,
            user_id=user_id,
            provider_reference=provider_reference
        )
        
        return kyc_request
    
    def get_kyc_request(
        self,
        kyc_request_id: int
    ) -> Optional[KYCRequest]:
        """Get KYC request by ID"""
        return self.db.query(KYCRequest).filter(KYCRequest.id == kyc_request_id).first()
    
    def get_kyc_request_by_provider_ref(
        self,
        provider_reference: str
    ) -> Optional[KYCRequest]:
        """Get KYC request by provider reference (for idempotency)"""
        return self.db.query(KYCRequest).filter(
            KYCRequest.provider_reference == provider_reference
        ).first()
    
    def get_user_kyc_requests(
        self,
        user_id: int,
        status_filter: Optional[KYCRequestStatus] = None
    ) -> List[KYCRequest]:
        """Get all KYC requests for a user"""
        query = self.db.query(KYCRequest).filter(KYCRequest.user_id == user_id)
        
        if status_filter:
            query = query.filter(KYCRequest.status == status_filter)
        
        return query.order_by(KYCRequest.submitted_at.desc()).all()
    
    async def process_webhook(
        self,
        provider_reference: str,
        verdict: Dict[str, Any],
        raw_response: Dict[str, Any],
        request_id: Optional[str] = None
    ) -> KYCRequest:
        """
        Process webhook from KYC provider
        
        Args:
            provider_reference: Provider's reference ID
            verdict: Provider's verdict data
            raw_response: Full provider response
            request_id: Optional request ID for correlation
            
        Returns:
            Updated KYCRequest object
            
        Raises:
            ValueError: If KYC request not found
        """
        # Idempotency check
        kyc_request = self.get_kyc_request_by_provider_ref(provider_reference)
        
        if not kyc_request:
            raise ValueError(f"KYC request not found for provider_reference: {provider_reference}")
        
        # Check if already processed
        if kyc_request.status in [KYCRequestStatus.APPROVED, KYCRequestStatus.REJECTED]:
            logger.info(
                "kyc_webhook_already_processed",
                kyc_request_id=kyc_request.id,
                provider_reference=provider_reference,
                current_status=kyc_request.status.value
            )
            return kyc_request
        
        # Update KYC request
        kyc_request.verdict = verdict
        kyc_request.raw_response = raw_response
        kyc_request.completed_at = datetime.utcnow()
        
        # Determine status from verdict
        result = verdict.get("result", "").lower()
        if result == "approved":
            kyc_request.status = KYCRequestStatus.APPROVED
        elif result == "rejected":
            kyc_request.status = KYCRequestStatus.REJECTED
        else:
            kyc_request.status = KYCRequestStatus.IN_REVIEW
        
        self.db.commit()
        self.db.refresh(kyc_request)
        
        # Audit log
        audit_service.log_system_action(
            db=self.db,
            action="kyc_webhook_received",
            target_type="kyc_request",
            target_id=kyc_request.id,
            meta={
                "provider_reference": provider_reference,
                "verdict": verdict,
                "status": kyc_request.status.value
            },
            request_id=request_id
        )
        
        logger.info(
            "kyc_webhook_processed",
            kyc_request_id=kyc_request.id,
            provider_reference=provider_reference,
            status=kyc_request.status.value
        )
        
        # TODO: Phase 5 - Trigger evaluate_kyc_verdict Celery task
        # await evaluate_kyc_verdict.delay(kyc_request.id, verdict)
        
        return kyc_request

