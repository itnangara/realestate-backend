"""
Integration tests for KYC workflow

Tests end-to-end KYC verification flow:
- Submit KYC → Webhook → Auto-approve role request
- Submit KYC → Webhook → Reject → Role request stays pending
- Webhook idempotency (duplicate webhooks)
- Webhook signature verification
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, Mock
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
def setup_kyc_tables(db_session):
    """
    Create tables needed for KYC workflow tests.
    
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
def test_user_with_roles(db_session, auth_service, test_roles):
    """Create test user with buyer role"""
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
def test_documents(db_session, test_user_with_roles):
    """Create test documents for the user"""
    documents = [
        Document(
            user_id=test_user_with_roles.id,
            type=DocumentType.ID_FRONT,
            s3_key="doc1.pdf",
            status=DocumentStatus.UPLOADED
        ),
        Document(
            user_id=test_user_with_roles.id,
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
def test_role_request(db_session, test_user_with_roles, test_documents):
    """Create test role request"""
    role_request = RoleRequest(
        user_id=test_user_with_roles.id,
        requested_roles=["seller", "agent"],
        status=RoleRequestStatus.PENDING,
        attachments=[doc.id for doc in test_documents]
    )
    db_session.add(role_request)
    db_session.commit()
    db_session.refresh(role_request)
    return role_request


class TestKYCWorkflow:
    """Tests for complete KYC workflow"""
    
    @pytest.mark.asyncio
    async def test_kyc_submit_via_service(self, db_session, test_user_with_roles, test_documents, test_role_request):
        """Test submitting KYC request via service"""
        from app.services.kyc_service import KYCService
        
        provider = MockKYCProvider()
        kyc_service = KYCService(db_session, provider)
        
        # Mock the Celery task - patch at the module level where it's imported
        with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_task:
            mock_task.delay = MagicMock()
            
            kyc_request = await kyc_service.submit_kyc_request(
                user_id=test_user_with_roles.id,
                document_ids=[doc.id for doc in test_documents],
                role_request_id=test_role_request.id
            )
            
            assert kyc_request is not None
            assert kyc_request.user_id == test_user_with_roles.id
            assert kyc_request.status == KYCRequestStatus.SUBMITTED
            assert kyc_request.provider_reference is not None
    
    @pytest.mark.asyncio
    async def test_kyc_webhook_approval(self, client, db_session, test_user_with_roles, test_documents, test_role_request):
        """Test KYC webhook with approval verdict"""
        from app.services.kyc_service import KYCService, MockKYCProvider
        
        # Submit KYC request
        provider = MockKYCProvider()
        kyc_service = KYCService(db_session, provider)
        
        # Mock Celery task for submission
        with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_task:
            mock_task.delay = MagicMock()
            
            kyc_request = await kyc_service.submit_kyc_request(
                user_id=test_user_with_roles.id,
                document_ids=[doc.id for doc in test_documents],
                role_request_id=test_role_request.id
            )
            
            provider_reference = kyc_request.provider_reference
            
            # Simulate webhook with approval
            webhook_payload = {
                "provider_reference": provider_reference,
                "verdict": {
                    "status": "approved",
                    "score": 0.95,
                    "risk_level": "low"
                },
                "result": "approved"
            }
            
            # Mock Celery task for webhook processing
            with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_eval, \
                 patch('app.services.notification_service.NotificationService.send_role_approval_notification', return_value=True):
                mock_eval.delay = MagicMock()
                
                # Process webhook
                response = client.post(
                    "/api/webhooks/kyc",
                    json=webhook_payload,
                    headers={"X-Signature": "test-signature", "X-Provider": "mock"}
                )
                
                assert response.status_code == status.HTTP_200_OK
                webhook_response = response.json()
                assert webhook_response["status"] == "success"
                
                # Verify KYC request status updated
                db_session.refresh(kyc_request)
                assert kyc_request.status in [KYCRequestStatus.APPROVED, KYCRequestStatus.IN_REVIEW]
                assert kyc_request.verdict is not None
    
    @pytest.mark.asyncio
    async def test_kyc_webhook_rejection(self, client, db_session, test_user_with_roles, test_documents, test_role_request):
        """Test KYC webhook with rejection verdict"""
        from app.services.kyc_service import KYCService, MockKYCProvider
        
        # Submit KYC request
        provider = MockKYCProvider()
        kyc_service = KYCService(db_session, provider)
        
        # Mock Celery task for submission
        with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_task:
            mock_task.delay = MagicMock()
            
            kyc_request = await kyc_service.submit_kyc_request(
                user_id=test_user_with_roles.id,
                document_ids=[doc.id for doc in test_documents],
                role_request_id=test_role_request.id
            )
            
            provider_reference = kyc_request.provider_reference
            
            # Simulate webhook with rejection
            # Note: The service looks for "result" inside verdict dict, not at top level
            webhook_payload = {
                "provider_reference": provider_reference,
                "verdict": {
                    "status": "rejected",
                    "reason": "Document quality insufficient",
                    "risk_level": "high",
                    "result": "rejected"  # result must be inside verdict
                }
            }
            
            # Mock Celery task for webhook processing
            with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_eval:
                mock_eval.delay = MagicMock()
                
                # Process webhook
                response = client.post(
                    "/api/webhooks/kyc",
                    json=webhook_payload,
                    headers={"X-Signature": "test-signature", "X-Provider": "mock"}
                )
                
                assert response.status_code == status.HTTP_200_OK
                
                # Verify KYC request status updated
                db_session.refresh(kyc_request)
                assert kyc_request.status == KYCRequestStatus.REJECTED
                assert kyc_request.verdict is not None
                
                # Verify role request stays pending (not auto-approved)
                db_session.refresh(test_role_request)
                assert test_role_request.status == RoleRequestStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_kyc_webhook_idempotency(self, client, db_session, test_user_with_roles, test_documents, test_role_request):
        """Test webhook idempotency - duplicate webhooks are handled gracefully"""
        from app.services.kyc_service import KYCService, MockKYCProvider
        
        # Submit KYC request
        provider = MockKYCProvider()
        kyc_service = KYCService(db_session, provider)
        
        # Mock Celery task for submission
        with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_task:
            mock_task.delay = MagicMock()
            
            kyc_request = await kyc_service.submit_kyc_request(
                user_id=test_user_with_roles.id,
                document_ids=[doc.id for doc in test_documents],
                role_request_id=test_role_request.id
            )
            
            provider_reference = kyc_request.provider_reference
            
            # First webhook
            webhook_payload = {
                "provider_reference": provider_reference,
                "verdict": {
                    "status": "approved",
                    "score": 0.95
                },
                "result": "approved"
            }
            
            # Mock Celery task for webhook processing
            with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_eval:
                mock_eval.delay = MagicMock()
                
                response1 = client.post(
                    "/api/webhooks/kyc",
                    json=webhook_payload,
                    headers={"X-Signature": "test-signature", "X-Provider": "mock"}
                )
                
                assert response1.status_code == status.HTTP_200_OK
                
                # Get the state after first webhook
                db_session.refresh(kyc_request)
                first_status = kyc_request.status
                first_verdict = kyc_request.verdict
                
                # Send duplicate webhook
                response2 = client.post(
                    "/api/webhooks/kyc",
                    json=webhook_payload,
                    headers={"X-Signature": "test-signature", "X-Provider": "mock"}
                )
                
                assert response2.status_code == status.HTTP_200_OK
                
                # Verify state hasn't changed (idempotent)
                db_session.refresh(kyc_request)
                assert kyc_request.status == first_status
                assert kyc_request.verdict == first_verdict
    
    @pytest.mark.asyncio
    async def test_kyc_webhook_invalid_signature(self, client, db_session, test_user_with_roles, test_documents, test_role_request):
        """Test webhook fails with invalid signature"""
        from app.services.kyc_service import KYCService, MockKYCProvider
        
        # Submit KYC request
        provider = MockKYCProvider()
        kyc_service = KYCService(db_session, provider)
        
        # Mock Celery task for submission
        with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_task:
            mock_task.delay = MagicMock()
            
            kyc_request = await kyc_service.submit_kyc_request(
                user_id=test_user_with_roles.id,
                document_ids=[doc.id for doc in test_documents],
                role_request_id=test_role_request.id
            )
            
            provider_reference = kyc_request.provider_reference
            
            webhook_payload = {
                "provider_reference": provider_reference,
                "verdict": {"status": "approved"},
                "result": "approved"
            }
            
            # Mock provider to return False for signature verification
            # Need to patch the factory to return a provider that fails verification
            mock_provider = MockKYCProvider()
            with patch.object(mock_provider, 'verify_webhook_signature', return_value=False), \
                 patch('app.services.kyc_provider_factory.get_kyc_provider', return_value=mock_provider):
                response = client.post(
                    "/api/webhooks/kyc",
                    json=webhook_payload,
                    headers={"X-Signature": "invalid-signature", "X-Provider": "mock"}
                )
                
                assert response.status_code == status.HTTP_401_UNAUTHORIZED
                assert "signature" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_kyc_webhook_missing_provider_reference(self, client):
        """Test webhook fails with missing provider_reference"""
        webhook_payload = {
            "verdict": {"status": "approved"},
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
    async def test_kyc_webhook_missing_verdict(self, client, db_session, test_user_with_roles, test_documents, test_role_request):
        """Test webhook fails with missing verdict"""
        from app.services.kyc_service import KYCService, MockKYCProvider
        
        # Submit KYC request
        provider = MockKYCProvider()
        kyc_service = KYCService(db_session, provider)
        
        # Mock Celery task for submission
        with patch('app.tasks.kyc_tasks.evaluate_kyc_verdict') as mock_task:
            mock_task.delay = MagicMock()
            
            kyc_request = await kyc_service.submit_kyc_request(
                user_id=test_user_with_roles.id,
                document_ids=[doc.id for doc in test_documents],
                role_request_id=test_role_request.id
            )
            
            provider_reference = kyc_request.provider_reference
            
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
    async def test_kyc_webhook_unknown_provider_reference(self, client):
        """Test webhook fails with unknown provider_reference"""
        webhook_payload = {
            "provider_reference": "unknown-ref-123",
            "verdict": {"status": "approved"},
            "result": "approved"
        }
        
        response = client.post(
            "/api/webhooks/kyc",
            json=webhook_payload,
            headers={"X-Signature": "test-signature", "X-Provider": "mock"}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND

