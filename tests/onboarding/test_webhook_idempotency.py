"""
Integration tests for webhook idempotency and security

Tests webhook handling:
- Valid signature → Process
- Invalid signature → Reject
- Duplicate webhook → Idempotent handling
- Missing required fields
- Unknown provider reference
"""

import pytest
from unittest.mock import patch, MagicMock, Mock
from fastapi import status
import json
import sys

# Mock Celery before importing anything that uses it
celery_mock = Mock()
celery_mock.Task = Mock()
celery_mock.exceptions = Mock()
celery_mock.exceptions.Retry = Exception  # Use Exception as base for Retry

sys.modules['celery'] = celery_mock
sys.modules['celery.task'] = Mock()
sys.modules['celery.app'] = Mock()
sys.modules['celery.exceptions'] = celery_mock.exceptions

from app.models.kyc_request import KYCRequest, KYCRequestStatus
from app.models.role_request import RoleRequest, RoleRequestStatus
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.services.kyc_service import MockKYCProvider


@pytest.fixture(scope="function", autouse=True)
def setup_webhook_tables(db_session):
    """
    Create tables needed for webhook idempotency tests.
    
    Uses ORM model creation - custom types handle SQLite compatibility automatically.
    """
    # Create User table first
    User.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create Role table
    Role.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create UserRole table
    UserRole.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create Document table
    Document.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create RoleRequest table
    RoleRequest.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create KYCRequest table
    KYCRequest.__table__.create(bind=db_session.bind, checkfirst=True)
    
    yield
    
    # Clean up
    try:
        KYCRequest.__table__.drop(bind=db_session.bind, checkfirst=True)
        RoleRequest.__table__.drop(bind=db_session.bind, checkfirst=True)
        Document.__table__.drop(bind=db_session.bind, checkfirst=True)
        UserRole.__table__.drop(bind=db_session.bind, checkfirst=True)
        Role.__table__.drop(bind=db_session.bind, checkfirst=True)
        User.__table__.drop(bind=db_session.bind, checkfirst=True)
    except Exception:
        pass


@pytest.fixture
def test_user(db_session, auth_service, test_roles):
    """Create test user"""
    hashed_password = auth_service.get_password_hash("testpass123")
    user = User(
        email="user@test.com",
        username="testuser",
        first_name="Test",
        last_name="User",
        hashed_password=hashed_password
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Assign buyer role
    buyer_role = db_session.query(Role).filter_by(name="buyer").first()
    user_role = UserRole(user_id=user.id, role_id=buyer_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


@pytest.fixture
def test_documents(db_session, test_user):
    """Create test documents"""
    documents = [
        Document(
            user_id=test_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="doc1.pdf",
            status=DocumentStatus.UPLOADED
        ),
        Document(
            user_id=test_user.id,
            type=DocumentType.ID_BACK,
            s3_key="doc2.pdf",
            status=DocumentStatus.UPLOADED
        )
    ]
    for doc in documents:
        db_session.add(doc)
    db_session.commit()
    for doc in documents:
        db_session.refresh(doc)
    return documents


@pytest.fixture
def test_kyc_request(db_session, test_user, test_documents):
    """Create test KYC request"""
    # Create KYC request directly for testing (simpler than going through service)
    kyc_request = KYCRequest(
        user_id=test_user.id,
        provider_reference=f"test-ref-{test_user.id}",
        status=KYCRequestStatus.SUBMITTED
    )
    db_session.add(kyc_request)
    db_session.commit()
    db_session.refresh(kyc_request)
    return kyc_request


class TestWebhookIdempotency:
    """Tests for webhook idempotency and security"""
    
    @pytest.mark.asyncio
    async def test_webhook_idempotency_same_payload(self, client, db_session, test_user, test_documents, test_kyc_request):
        """Test that duplicate webhooks with same payload are idempotent"""
        provider_reference = test_kyc_request.provider_reference
        
        webhook_payload = {
            "provider_reference": provider_reference,
            "verdict": {
                "status": "approved",
                "score": 0.95,
                "risk_level": "low"
            },
            "result": "approved"
        }
        
        with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_eval:
            mock_eval.delay = MagicMock()
            
            # First webhook
            response1 = client.post(
                "/api/webhooks/kyc",
                json=webhook_payload,
                headers={"X-Signature": "test-signature", "X-Provider": "mock"}
            )
            
            assert response1.status_code == status.HTTP_200_OK
            
            # Get state after first webhook
            db_session.refresh(test_kyc_request)
            first_status = test_kyc_request.status
            first_verdict = test_kyc_request.verdict
            
            # Second webhook (duplicate)
            response2 = client.post(
                "/api/webhooks/kyc",
                json=webhook_payload,
                headers={"X-Signature": "test-signature", "X-Provider": "mock"}
            )
            
            assert response2.status_code == status.HTTP_200_OK
            
            # Verify business logic is idempotent (status and verdict don't change)
            # Note: completed_at may be updated, but business state should remain same
            db_session.refresh(test_kyc_request)
            assert test_kyc_request.status == first_status, f"Status changed from {first_status} to {test_kyc_request.status}"
            assert test_kyc_request.verdict == first_verdict, "Verdict changed on duplicate webhook"
    
    @pytest.mark.asyncio
    async def test_webhook_idempotency_different_payload_same_ref(self, client, db_session, test_user, test_documents, test_kyc_request):
        """Test that webhooks with same provider_reference but different payloads are idempotent"""
        provider_reference = test_kyc_request.provider_reference
        
        # First webhook
        webhook_payload1 = {
            "provider_reference": provider_reference,
            "verdict": {
                "status": "approved",
                "score": 0.95
            },
            "result": "approved"
        }
        
        with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_eval:
            mock_eval.delay = MagicMock()
            
            response1 = client.post(
                "/api/webhooks/kyc",
                json=webhook_payload1,
                headers={"X-Signature": "test-signature", "X-Provider": "mock"}
            )
            
            assert response1.status_code == status.HTTP_200_OK
            
            # Get state after first webhook
            db_session.refresh(test_kyc_request)
            first_status = test_kyc_request.status
            
            # Second webhook with different payload but same provider_reference
            webhook_payload2 = {
                "provider_reference": provider_reference,
                "verdict": {
                    "status": "approved",
                    "score": 0.98,  # Different score
                    "additional_field": "new_data"
                },
                "result": "approved"
            }
            
            response2 = client.post(
                "/api/webhooks/kyc",
                json=webhook_payload2,
                headers={"X-Signature": "test-signature", "X-Provider": "mock"}
            )
            
            assert response2.status_code == status.HTTP_200_OK
            
            # Verify status hasn't changed (idempotent by provider_reference)
            db_session.refresh(test_kyc_request)
            assert test_kyc_request.status == first_status
    
    @pytest.mark.asyncio
    async def test_webhook_valid_signature(self, client, db_session, test_user, test_documents, test_kyc_request):
        """Test webhook with valid signature is processed"""
        provider_reference = test_kyc_request.provider_reference
        
        webhook_payload = {
            "provider_reference": provider_reference,
            "verdict": {
                "status": "approved",
                "score": 0.95
            },
            "result": "approved"
        }
        
        # Mock provider to return True for signature verification
        provider = MockKYCProvider()
        with patch.object(provider, 'verify_webhook_signature', return_value=True), \
             patch('app.services.kyc_provider_factory.get_kyc_provider', return_value=provider), \
             patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_eval:
            mock_eval.delay = MagicMock()
            
            response = client.post(
                "/api/webhooks/kyc",
                json=webhook_payload,
                headers={"X-Signature": "valid-signature", "X-Provider": "mock"}
            )
            
            assert response.status_code == status.HTTP_200_OK
    
    @pytest.mark.asyncio
    async def test_webhook_invalid_signature(self, client, db_session, test_user, test_documents, test_kyc_request):
        """Test webhook with invalid signature is rejected"""
        provider_reference = test_kyc_request.provider_reference
        
        webhook_payload = {
            "provider_reference": provider_reference,
            "verdict": {
                "status": "approved",
                "score": 0.95
            },
            "result": "approved"
        }
        
        # Mock provider to return False for signature verification
        provider = MockKYCProvider()
        with patch.object(provider, 'verify_webhook_signature', return_value=False), \
             patch('app.services.kyc_provider_factory.get_kyc_provider', return_value=provider), \
             patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_eval:
            mock_eval.delay = MagicMock()
            
            response = client.post(
                "/api/webhooks/kyc",
                json=webhook_payload,
                headers={"X-Signature": "invalid-signature", "X-Provider": "mock"}
            )
            
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "signature" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_webhook_missing_provider_reference(self, client):
        """Test webhook fails without provider_reference"""
        webhook_payload = {
            "verdict": {
                "status": "approved",
                "score": 0.95
            },
            "result": "approved"
        }
        
        response = client.post(
            "/api/webhooks/kyc",
            json=webhook_payload,
            headers={"X-Signature": "test-signature", "X-Provider": "mock"}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "provider_reference" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_webhook_missing_verdict(self, client, db_session, test_user, test_documents, test_kyc_request):
        """Test webhook fails without verdict"""
        provider_reference = test_kyc_request.provider_reference
        
        webhook_payload = {
            "provider_reference": provider_reference
        }
        
        response = client.post(
            "/api/webhooks/kyc",
            json=webhook_payload,
            headers={"X-Signature": "test-signature", "X-Provider": "mock"}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "verdict" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_webhook_unknown_provider_reference(self, client):
        """Test webhook fails with unknown provider_reference"""
        webhook_payload = {
            "provider_reference": "unknown-ref-12345",
            "verdict": {
                "status": "approved",
                "score": 0.95
            },
            "result": "approved"
        }
        
        response = client.post(
            "/api/webhooks/kyc",
            json=webhook_payload,
            headers={"X-Signature": "test-signature", "X-Provider": "mock"}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_webhook_invalid_json(self, client):
        """Test webhook fails with invalid JSON"""
        response = client.post(
            "/api/webhooks/kyc",
            data="invalid json",
            headers={"Content-Type": "application/json", "X-Signature": "test-signature", "X-Provider": "mock"}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    @pytest.mark.asyncio
    async def test_webhook_without_signature_header(self, client, db_session, test_user, test_documents, test_kyc_request):
        """Test webhook processes without signature header (optional)"""
        provider_reference = test_kyc_request.provider_reference
        
        webhook_payload = {
            "provider_reference": provider_reference,
            "verdict": {
                "status": "approved",
                "score": 0.95
            },
            "result": "approved"
        }
        
        with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_eval:
            mock_eval.delay = MagicMock()
            
            # Webhook without signature header should still work
            response = client.post(
                "/api/webhooks/kyc",
                json=webhook_payload,
                headers={"X-Provider": "mock"}
            )
            
            # Should succeed (signature is optional, but if provided must be valid)
            assert response.status_code == status.HTTP_200_OK
    
    @pytest.mark.asyncio
    async def test_webhook_status_transitions(self, client, db_session, test_user, test_documents, test_kyc_request):
        """Test webhook correctly updates KYC request status"""
        provider_reference = test_kyc_request.provider_reference
        
        # Verify initial status
        assert test_kyc_request.status == KYCRequestStatus.SUBMITTED
        
        # Send approval webhook
        webhook_payload = {
            "provider_reference": provider_reference,
            "verdict": {
                "status": "approved",
                "score": 0.95,
                "risk_level": "low"
            },
            "result": "approved"
        }
        
        with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_eval:
            mock_eval.delay = MagicMock()
            
            response = client.post(
                "/api/webhooks/kyc",
                json=webhook_payload,
                headers={"X-Signature": "test-signature", "X-Provider": "mock"}
            )
            
            assert response.status_code == status.HTTP_200_OK
            
            # Verify status updated
            db_session.refresh(test_kyc_request)
            assert test_kyc_request.status in [KYCRequestStatus.APPROVED, KYCRequestStatus.IN_REVIEW]
            assert test_kyc_request.verdict is not None
            assert test_kyc_request.completed_at is not None

