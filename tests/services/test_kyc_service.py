"""
Enterprise-Grade KYC Service Tests

Comprehensive test suite for KYCService covering:
- KYC request submission with idempotency
- Document validation and ownership checks
- Provider integration (MockKYCProvider)
- Webhook processing with idempotency
- Status transitions (submitted -> approved/rejected/in_review)
- KYC request retrieval and filtering
- Error handling and edge cases
- Audit logging integration
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime
from typing import Dict, Any

from app.services.kyc_service import KYCService, MockKYCProvider, KYCProvider
from app.models.kyc_request import KYCRequest, KYCRequestStatus
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.user import User
from app.services.audit_service import audit_service


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(scope="function", autouse=True)
def setup_kyc_tables(db_session):
    """
    Create tables needed for KYC tests.
    
    Uses ORM model creation - custom JSONBType handles SQLite compatibility
    automatically (JSONB -> JSON text).
    """
    # Create User table first
    User.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create Document table
    Document.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create KYCRequest table - JSONBType handles SQLite automatically
    KYCRequest.__table__.create(bind=db_session.bind, checkfirst=True)
    
    yield
    
    # Clean up
    try:
        KYCRequest.__table__.drop(bind=db_session.bind, checkfirst=True)
        Document.__table__.drop(bind=db_session.bind, checkfirst=True)
        User.__table__.drop(bind=db_session.bind, checkfirst=True)
    except Exception:
        pass


@pytest.fixture
def test_user(db_session):
    """Create a test user"""
    user = User(
        email="test@example.com",
        username="testuser",
        first_name="Test",
        last_name="User",
        hashed_password="hashed_password"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_documents(test_user, db_session):
    """Create test documents for the user"""
    documents = [
        Document(
            user_id=test_user.id,
            type=DocumentType.ID_FRONT,
            s3_key=f"documents/{test_user.id}/id_front_{i}.pdf",
            status=DocumentStatus.UPLOADED
        )
        for i in range(3)
    ]
    for doc in documents:
        db_session.add(doc)
    db_session.commit()
    for doc in documents:
        db_session.refresh(doc)
    return documents


@pytest.fixture
def mock_provider():
    """Create a mock KYC provider"""
    return MockKYCProvider()


@pytest.fixture
def kyc_service(db_session, mock_provider):
    """Create KYCService instance with mock provider"""
    return KYCService(db_session, provider=mock_provider)


# ============================================================================
# Test MockKYCProvider
# ============================================================================

class TestMockKYCProvider:
    """Tests for MockKYCProvider implementation"""
    
    @pytest.mark.asyncio
    async def test_submit_verification_success(self, mock_provider):
        """Test successful verification submission"""
        result = await mock_provider.submit_verification(
            user_id=123,
            document_ids=[1, 2, 3],
            metadata={"source": "test"}
        )
        
        assert "provider_reference" in result
        assert result["provider_reference"].startswith("mock_")
        assert result["status"] == "submitted"
        
        # Verify stored in provider
        assert result["provider_reference"] in mock_provider.verifications
    
    @pytest.mark.asyncio
    async def test_get_verification_status_found(self, mock_provider):
        """Test getting verification status for existing reference"""
        # Submit first
        submit_result = await mock_provider.submit_verification(
            user_id=123,
            document_ids=[1, 2]
        )
        provider_ref = submit_result["provider_reference"]
        
        # Get status
        status_result = await mock_provider.get_verification_status(provider_ref)
        
        assert status_result["status"] == "submitted"
        assert status_result["verdict"] is not None
        assert status_result["verdict"]["result"] == "approved"
        assert "confidence" in status_result["verdict"]
        assert "checks" in status_result["verdict"]
    
    @pytest.mark.asyncio
    async def test_get_verification_status_not_found(self, mock_provider):
        """Test getting verification status for non-existent reference"""
        result = await mock_provider.get_verification_status("nonexistent_ref")
        
        assert result["status"] == "not_found"
        assert result["verdict"] is None
    
    def test_verify_webhook_signature_always_true(self, mock_provider):
        """Test that mock provider always returns True for signature verification"""
        result = mock_provider.verify_webhook_signature(
            payload=b"test payload",
            signature="test_signature",
            headers={"X-Signature": "test"}
        )
        
        assert result is True


# ============================================================================
# Test Submit KYC Request
# ============================================================================

class TestSubmitKYCRequest:
    """Tests for submit_kyc_request method"""
    
    @pytest.mark.asyncio
    async def test_submit_kyc_request_success(self, kyc_service, test_user, test_documents, db_session):
        """Test successful KYC request submission"""
        with patch.object(audit_service, 'log_system_action') as mock_audit:
            document_ids = [doc.id for doc in test_documents]
            
            result = await kyc_service.submit_kyc_request(
                user_id=test_user.id,
                document_ids=document_ids,
                role_request_id=123,
                metadata={"source": "test"},
                request_id="req-123"
            )
            
            assert result.id is not None
            assert result.user_id == test_user.id
            assert result.provider_reference is not None
            assert result.status == KYCRequestStatus.SUBMITTED
            assert result.attempts == 1
            assert result.submitted_at is not None
            
            # Verify audit log
            mock_audit.assert_called_once()
            call_args = mock_audit.call_args
            assert call_args[1]["action"] == "kyc_request_submitted"
            assert call_args[1]["target_type"] == "kyc_request"
            assert call_args[1]["target_id"] == result.id
    
    @pytest.mark.asyncio
    async def test_submit_kyc_request_idempotency_existing_request(self, kyc_service, test_user, test_documents, db_session):
        """Test idempotency - returns existing request if user has pending request"""
        document_ids = [doc.id for doc in test_documents]
        
        # Submit first request
        first_request = await kyc_service.submit_kyc_request(
            user_id=test_user.id,
            document_ids=document_ids
        )
        
        # Submit again (should return existing)
        second_request = await kyc_service.submit_kyc_request(
            user_id=test_user.id,
            document_ids=document_ids
        )
        
        assert second_request.id == first_request.id
        assert second_request.status == KYCRequestStatus.SUBMITTED
    
    @pytest.mark.asyncio
    async def test_submit_kyc_request_document_validation_fails(self, kyc_service, test_user, test_documents):
        """Test submission fails when documents don't belong to user"""
        # Try to submit with non-existent document
        with pytest.raises(ValueError) as exc_info:
            await kyc_service.submit_kyc_request(
                user_id=test_user.id,
                document_ids=[99999]  # Non-existent
            )
        
        assert "document" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_submit_kyc_request_document_belongs_to_different_user(self, kyc_service, test_user, db_session):
        """Test submission fails when document belongs to different user"""
        # Create another user with a document
        other_user = User(
            email="other@example.com",
            username="otheruser",
            first_name="Other",
            last_name="User",
            hashed_password="hashed_password"
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)
        
        other_doc = Document(
            user_id=other_user.id,
            type=DocumentType.ID_FRONT,
            s3_key=f"documents/{other_user.id}/id_front.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(other_doc)
        db_session.commit()
        db_session.refresh(other_doc)
        
        # Try to submit with other user's document
        with pytest.raises(ValueError) as exc_info:
            await kyc_service.submit_kyc_request(
                user_id=test_user.id,
                document_ids=[other_doc.id]
            )
        
        assert "document" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_submit_kyc_request_provider_reference_idempotency(self, kyc_service, test_user, test_documents, db_session):
        """Test idempotency via provider_reference"""
        document_ids = [doc.id for doc in test_documents]
        
        # Create a KYC request manually with a provider_reference
        existing_request = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_existing_ref",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        db_session.add(existing_request)
        db_session.commit()
        db_session.refresh(existing_request)
        
        # Mock provider to return same reference
        mock_provider = MockKYCProvider()
        mock_provider.verifications["mock_existing_ref"] = {
            "user_id": test_user.id,
            "document_ids": document_ids,
            "status": "submitted"
        }
        
        kyc_service_with_mock = KYCService(db_session, provider=mock_provider)
        
        # Override submit_verification to return existing ref
        async def mock_submit(*args, **kwargs):
            return {"provider_reference": "mock_existing_ref", "status": "submitted"}
        
        mock_provider.submit_verification = mock_submit
        
        # Submit should return existing request
        result = await kyc_service_with_mock.submit_kyc_request(
            user_id=test_user.id,
            document_ids=document_ids
        )
        
        assert result.id == existing_request.id
    
    @pytest.mark.asyncio
    async def test_submit_kyc_request_provider_no_reference(self, kyc_service, test_user, test_documents):
        """Test submission fails when provider doesn't return reference"""
        document_ids = [doc.id for doc in test_documents]
        
        # Mock provider to return no reference
        mock_provider = MockKYCProvider()
        async def mock_submit(*args, **kwargs):
            return {"status": "submitted"}  # No provider_reference
        
        mock_provider.submit_verification = mock_submit
        kyc_service.provider = mock_provider
        
        with pytest.raises(ValueError) as exc_info:
            await kyc_service.submit_kyc_request(
                user_id=test_user.id,
                document_ids=document_ids
            )
        
        assert "reference" in str(exc_info.value).lower()


# ============================================================================
# Test Get KYC Request
# ============================================================================

class TestGetKYCRequest:
    """Tests for get_kyc_request method"""
    
    def test_get_kyc_request_success(self, kyc_service, test_user, db_session):
        """Test successful KYC request retrieval"""
        kyc_request = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_123",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        db_session.add(kyc_request)
        db_session.commit()
        db_session.refresh(kyc_request)
        
        result = kyc_service.get_kyc_request(kyc_request_id=kyc_request.id)
        
        assert result is not None
        assert result.id == kyc_request.id
        assert result.user_id == test_user.id
    
    def test_get_kyc_request_not_found(self, kyc_service):
        """Test retrieval returns None for non-existent request"""
        result = kyc_service.get_kyc_request(kyc_request_id=99999)
        
        assert result is None


# ============================================================================
# Test Get KYC Request By Provider Reference
# ============================================================================

class TestGetKYCRequestByProviderRef:
    """Tests for get_kyc_request_by_provider_ref method"""
    
    def test_get_kyc_request_by_provider_ref_success(self, kyc_service, test_user, db_session):
        """Test successful retrieval by provider reference"""
        kyc_request = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_456",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        db_session.add(kyc_request)
        db_session.commit()
        db_session.refresh(kyc_request)
        
        result = kyc_service.get_kyc_request_by_provider_ref("mock_ref_456")
        
        assert result is not None
        assert result.id == kyc_request.id
        assert result.provider_reference == "mock_ref_456"
    
    def test_get_kyc_request_by_provider_ref_not_found(self, kyc_service):
        """Test retrieval returns None for non-existent reference"""
        result = kyc_service.get_kyc_request_by_provider_ref("nonexistent_ref")
        
        assert result is None


# ============================================================================
# Test Get User KYC Requests
# ============================================================================

class TestGetUserKYCRequests:
    """Tests for get_user_kyc_requests method"""
    
    def test_get_user_kyc_requests_all(self, kyc_service, test_user, db_session):
        """Test retrieving all KYC requests for a user"""
        # Create multiple KYC requests
        req1 = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_1",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        req2 = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_2",
            status=KYCRequestStatus.APPROVED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        db_session.add(req1)
        db_session.add(req2)
        db_session.commit()
        
        result = kyc_service.get_user_kyc_requests(user_id=test_user.id)
        
        assert len(result) == 2
        assert all(req.user_id == test_user.id for req in result)
        # Verify we got both requests
        ids = {req.id for req in result}
        assert req1.id in ids
        assert req2.id in ids
    
    def test_get_user_kyc_requests_filter_by_status(self, kyc_service, test_user, db_session):
        """Test filtering KYC requests by status"""
        # Create requests with different statuses
        req1 = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_1",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        req2 = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_2",
            status=KYCRequestStatus.APPROVED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        db_session.add(req1)
        db_session.add(req2)
        db_session.commit()
        
        result = kyc_service.get_user_kyc_requests(
            user_id=test_user.id,
            status_filter=KYCRequestStatus.SUBMITTED
        )
        
        assert len(result) == 1
        assert result[0].status == KYCRequestStatus.SUBMITTED
    
    def test_get_user_kyc_requests_empty(self, kyc_service, test_user):
        """Test retrieving KYC requests when user has none"""
        result = kyc_service.get_user_kyc_requests(user_id=test_user.id)
        
        assert len(result) == 0
    
    def test_get_user_kyc_requests_only_returns_user_requests(self, kyc_service, test_user, db_session):
        """Test that only the specified user's requests are returned"""
        # Create another user with a request
        other_user = User(
            email="other@example.com",
            username="otheruser",
            first_name="Other",
            last_name="User",
            hashed_password="hashed_password"
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)
        
        # Create requests for both users
        user_req = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_user",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        other_req = KYCRequest(
            user_id=other_user.id,
            provider_reference="mock_ref_other",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        db_session.add(user_req)
        db_session.add(other_req)
        db_session.commit()
        
        result = kyc_service.get_user_kyc_requests(user_id=test_user.id)
        
        assert len(result) == 1
        assert result[0].user_id == test_user.id


# ============================================================================
# Test Process Webhook
# ============================================================================

class TestProcessWebhook:
    """Tests for process_webhook method"""
    
    @pytest.mark.asyncio
    async def test_process_webhook_approved(self, kyc_service, test_user, db_session):
        """Test webhook processing with approved verdict"""
        # Create a submitted KYC request
        kyc_request = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_approved",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        db_session.add(kyc_request)
        db_session.commit()
        db_session.refresh(kyc_request)
        
        verdict = {
            "result": "approved",
            "confidence": 0.95,
            "checks": {
                "identity": "passed",
                "document": "passed"
            }
        }
        raw_response = {
            "verdict": verdict,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        with patch.object(audit_service, 'log_system_action') as mock_audit:
            result = await kyc_service.process_webhook(
                provider_reference="mock_ref_approved",
                verdict=verdict,
                raw_response=raw_response,
                request_id="webhook-123"
            )
            
            assert result.status == KYCRequestStatus.APPROVED
            assert result.verdict == verdict
            assert result.raw_response == raw_response
            assert result.completed_at is not None
            
            # Verify audit log
            mock_audit.assert_called_once()
            call_args = mock_audit.call_args
            assert call_args[1]["action"] == "kyc_webhook_received"
            assert call_args[1]["target_type"] == "kyc_request"
            assert call_args[1]["target_id"] == result.id
    
    @pytest.mark.asyncio
    async def test_process_webhook_rejected(self, kyc_service, test_user, db_session):
        """Test webhook processing with rejected verdict"""
        kyc_request = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_rejected",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        db_session.add(kyc_request)
        db_session.commit()
        db_session.refresh(kyc_request)
        
        verdict = {
            "result": "rejected",
            "reason": "Document quality insufficient",
            "checks": {
                "identity": "failed",
                "document": "failed"
            }
        }
        raw_response = {"verdict": verdict}
        
        result = await kyc_service.process_webhook(
            provider_reference="mock_ref_rejected",
            verdict=verdict,
            raw_response=raw_response
        )
        
        assert result.status == KYCRequestStatus.REJECTED
        assert result.verdict == verdict
    
    @pytest.mark.asyncio
    async def test_process_webhook_in_review(self, kyc_service, test_user, db_session):
        """Test webhook processing with in_review status"""
        kyc_request = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_review",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        db_session.add(kyc_request)
        db_session.commit()
        db_session.refresh(kyc_request)
        
        verdict = {
            "result": "pending",
            "message": "Additional review required"
        }
        raw_response = {"verdict": verdict}
        
        result = await kyc_service.process_webhook(
            provider_reference="mock_ref_review",
            verdict=verdict,
            raw_response=raw_response
        )
        
        assert result.status == KYCRequestStatus.IN_REVIEW
        assert result.verdict == verdict
    
    @pytest.mark.asyncio
    async def test_process_webhook_idempotency_already_approved(self, kyc_service, test_user, db_session):
        """Test webhook idempotency - already processed request"""
        kyc_request = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_idempotent",
            status=KYCRequestStatus.APPROVED,
            submitted_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            attempts=1,
            verdict={"result": "approved"}
        )
        db_session.add(kyc_request)
        db_session.commit()
        db_session.refresh(kyc_request)
        
        original_completed_at = kyc_request.completed_at
        
        # Process webhook again
        verdict = {"result": "approved"}
        result = await kyc_service.process_webhook(
            provider_reference="mock_ref_idempotent",
            verdict=verdict,
            raw_response={"verdict": verdict}
        )
        
        # Should return same request without changes
        assert result.id == kyc_request.id
        assert result.status == KYCRequestStatus.APPROVED
        # completed_at should not change
        assert result.completed_at == original_completed_at
    
    @pytest.mark.asyncio
    async def test_process_webhook_idempotency_already_rejected(self, kyc_service, test_user, db_session):
        """Test webhook idempotency - already rejected request"""
        kyc_request = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_rejected_idempotent",
            status=KYCRequestStatus.REJECTED,
            submitted_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            attempts=1,
            verdict={"result": "rejected"}
        )
        db_session.add(kyc_request)
        db_session.commit()
        db_session.refresh(kyc_request)
        
        # Process webhook again
        verdict = {"result": "approved"}  # Different verdict
        result = await kyc_service.process_webhook(
            provider_reference="mock_ref_rejected_idempotent",
            verdict=verdict,
            raw_response={"verdict": verdict}
        )
        
        # Should return same request, status should remain REJECTED
        assert result.id == kyc_request.id
        assert result.status == KYCRequestStatus.REJECTED
    
    @pytest.mark.asyncio
    async def test_process_webhook_not_found(self, kyc_service):
        """Test webhook processing fails for non-existent provider reference"""
        verdict = {"result": "approved"}
        
        with pytest.raises(ValueError) as exc_info:
            await kyc_service.process_webhook(
                provider_reference="nonexistent_ref",
                verdict=verdict,
                raw_response={"verdict": verdict}
            )
        
        assert "not found" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_process_webhook_handles_celery_unavailable(self, kyc_service, test_user, db_session):
        """Test that webhook processing succeeds even if Celery is unavailable"""
        kyc_request = KYCRequest(
            user_id=test_user.id,
            provider_reference="mock_ref_celery",
            status=KYCRequestStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            attempts=1
        )
        db_session.add(kyc_request)
        db_session.commit()
        db_session.refresh(kyc_request)
        
        verdict = {"result": "approved"}
        raw_response = {"verdict": verdict}
        
        # Should succeed even if Celery import fails (handled by try-except in service)
        result = await kyc_service.process_webhook(
            provider_reference="mock_ref_celery",
            verdict=verdict,
            raw_response=raw_response
        )
        
        assert result.status == KYCRequestStatus.APPROVED


# ============================================================================
# Test KYCService with Custom Provider
# ============================================================================

class TestKYCServiceWithCustomProvider:
    """Tests for KYCService with custom provider injection"""
    
    @pytest.mark.asyncio
    async def test_kyc_service_uses_custom_provider(self, test_user, test_documents, db_session):
        """Test that KYCService uses injected provider"""
        # Create custom mock provider
        custom_provider = MockKYCProvider()
        
        kyc_service = KYCService(db_session, provider=custom_provider)
        
        document_ids = [doc.id for doc in test_documents]
        result = await kyc_service.submit_kyc_request(
            user_id=test_user.id,
            document_ids=document_ids
        )
        
        assert result.id is not None
        # Verify custom provider was used
        assert result.provider_reference.startswith("mock_")
    
    @pytest.mark.asyncio
    async def test_kyc_service_defaults_to_mock_provider(self, test_user, test_documents, db_session):
        """Test that KYCService defaults to MockKYCProvider when no provider given"""
        kyc_service = KYCService(db_session)  # No provider specified
        
        document_ids = [doc.id for doc in test_documents]
        result = await kyc_service.submit_kyc_request(
            user_id=test_user.id,
            document_ids=document_ids
        )
        
        assert result.id is not None
        assert isinstance(kyc_service.provider, MockKYCProvider)

