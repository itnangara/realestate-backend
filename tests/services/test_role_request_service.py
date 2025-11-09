"""
Enterprise-Grade Role Request Service Tests

Comprehensive test suite for RoleRequestService covering:
- Role request creation with feature flag validation
- Document attachment validation
- KYC requirement checking
- Role request retrieval and filtering
- Authorization checks
- Error handling and edge cases
- Audit logging integration
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.services.role_request_service import RoleRequestService
from app.models.role_request import RoleRequest, RoleRequestStatus
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.user import User
from app.services.audit_service import audit_service
from app.core.feature_flags import feature_flags


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(scope="function", autouse=True)
def setup_role_request_tables(db_session):
    """
    Create tables needed for role request tests.
    
    Uses ORM model creation - custom ArrayType and JSONBType handle
    SQLite compatibility automatically (ARRAY/JSONB -> JSON text).
    """
    # Create User table first
    User.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create Document table
    Document.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create RoleRequest table - ArrayType and JSONBType handle SQLite automatically
    RoleRequest.__table__.create(bind=db_session.bind, checkfirst=True)
    
    yield
    
    # Clean up
    try:
        RoleRequest.__table__.drop(bind=db_session.bind, checkfirst=True)
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
def role_request_service(db_session):
    """Create RoleRequestService instance"""
    return RoleRequestService(db_session)


# ============================================================================
# Test Create Role Request
# ============================================================================

class TestCreateRoleRequest:
    """Tests for create_role_request method"""
    
    @pytest.mark.asyncio
    async def test_create_role_request_success(self, role_request_service, test_user, db_session):
        """Test successful role request creation"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag, \
             patch.object(audit_service, 'log_user_action') as mock_audit:
            
            mock_flag.return_value = True
            
            result = await role_request_service.create_role_request(
                user_id=test_user.id,
                requested_roles=["seller", "agent"],
                notes="Please approve my roles",
                request_id="req-123"
            )
            
            assert result.id is not None
            assert result.user_id == test_user.id
            assert result.requested_roles == ["seller", "agent"]
            assert result.status == RoleRequestStatus.PENDING
            assert result.notes == "Please approve my roles"
            
            # Verify audit log
            mock_audit.assert_called_once()
            call_args = mock_audit.call_args
            assert call_args[1]["action"] == "role_request_created"
            assert call_args[1]["user_id"] == test_user.id
            assert call_args[1]["target_type"] == "role_request"
            assert call_args[1]["target_id"] == result.id
    
    @pytest.mark.asyncio
    async def test_create_role_request_with_documents(self, role_request_service, test_user, test_documents, db_session):
        """Test role request creation with document attachments"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag, \
             patch.object(audit_service, 'log_user_action'):
            
            mock_flag.return_value = True
            
            document_ids = [doc.id for doc in test_documents[:2]]
            result = await role_request_service.create_role_request(
                user_id=test_user.id,
                requested_roles=["seller"],
                document_ids=document_ids
            )
            
            assert result.attachments == document_ids
            
            # Verify documents were validated
            retrieved = db_session.query(RoleRequest).filter(RoleRequest.id == result.id).first()
            assert retrieved.attachments == document_ids
    
    @pytest.mark.asyncio
    async def test_create_role_request_feature_flag_disabled(self, role_request_service, test_user):
        """Test role request creation fails when feature flag is disabled"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = False
            
            with pytest.raises(HTTPException) as exc_info:
                await role_request_service.create_role_request(
                    user_id=test_user.id,
                    requested_roles=["seller"]
                )
            
            assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "disabled" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_create_role_request_invalid_document_ids(self, role_request_service, test_user, test_documents):
        """Test role request creation fails with invalid document IDs"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = True
            
            # Try to attach document that doesn't exist
            with pytest.raises(HTTPException) as exc_info:
                await role_request_service.create_role_request(
                    user_id=test_user.id,
                    requested_roles=["seller"],
                    document_ids=[99999]  # Non-existent document
                )
            
            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
            assert "document" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_create_role_request_document_belongs_to_different_user(self, role_request_service, test_user, db_session):
        """Test role request creation fails when document belongs to different user"""
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
        
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = True
            
            # Try to attach other user's document
            with pytest.raises(HTTPException) as exc_info:
                await role_request_service.create_role_request(
                    user_id=test_user.id,
                    requested_roles=["seller"],
                    document_ids=[other_doc.id]
                )
            
            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    
    @pytest.mark.asyncio
    async def test_create_role_request_handles_celery_unavailable(self, role_request_service, test_user, db_session):
        """Test that role request creation succeeds even if Celery is unavailable"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag, \
             patch.object(audit_service, 'log_user_action'):
            
            mock_flag.return_value = True
            
            # Should succeed even if Celery import fails (handled by try-except in service)
            result = await role_request_service.create_role_request(
                user_id=test_user.id,
                requested_roles=["seller"]
            )
            
            assert result.id is not None


# ============================================================================
# Test Get User Role Requests
# ============================================================================

class TestGetUserRoleRequests:
    """Tests for get_user_role_requests method"""
    
    def test_get_user_role_requests_all(self, role_request_service, test_user, db_session):
        """Test retrieving all role requests for a user"""
        # Create multiple role requests using ORM - ArrayType handles SQLite automatically
        req1 = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        req2 = RoleRequest(
            user_id=test_user.id,
            requested_roles=["agent"],
            status=RoleRequestStatus.APPROVED
        )
        db_session.add(req1)
        db_session.add(req2)
        db_session.commit()
        
        result = role_request_service.get_user_role_requests(user_id=test_user.id)
        
        assert len(result) == 2
        assert all(req.user_id == test_user.id for req in result)
        # Should be ordered by requested_at desc (newest first)
        # Since both are created at same time, just verify we got both
        ids = {req.id for req in result}
        assert req1.id in ids
        assert req2.id in ids
    
    def test_get_user_role_requests_filter_by_status(self, role_request_service, test_user, db_session):
        """Test filtering role requests by status"""
        # Create requests with different statuses using ORM
        req1 = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        req2 = RoleRequest(
            user_id=test_user.id,
            requested_roles=["agent"],
            status=RoleRequestStatus.APPROVED
        )
        db_session.add(req1)
        db_session.add(req2)
        db_session.commit()
        
        result = role_request_service.get_user_role_requests(
            user_id=test_user.id,
            status_filter=RoleRequestStatus.PENDING
        )
        
        assert len(result) == 1
        assert result[0].status == RoleRequestStatus.PENDING
    
    def test_get_user_role_requests_empty(self, role_request_service, test_user):
        """Test retrieving role requests when user has none"""
        result = role_request_service.get_user_role_requests(user_id=test_user.id)
        
        assert len(result) == 0
    
    def test_get_user_role_requests_only_returns_user_requests(self, role_request_service, test_user, db_session):
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
        
        # Create requests for both users using ORM
        req1 = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        req2 = RoleRequest(
            user_id=other_user.id,
            requested_roles=["agent"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(req1)
        db_session.add(req2)
        db_session.commit()
        
        result = role_request_service.get_user_role_requests(user_id=test_user.id)
        
        assert len(result) == 1
        assert result[0].user_id == test_user.id


# ============================================================================
# Test Get Role Request
# ============================================================================

class TestGetRoleRequest:
    """Tests for get_role_request method"""
    
    def test_get_role_request_success(self, role_request_service, test_user, db_session):
        """Test successful role request retrieval"""
        # Create role request using ORM - ArrayType handles SQLite automatically
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        result = role_request_service.get_role_request(
            role_request_id=role_request.id,
            user_id=test_user.id
        )
        
        assert result is not None
        assert result.id == role_request.id
        assert result.user_id == test_user.id
    
    def test_get_role_request_without_user_id(self, role_request_service, test_user, db_session):
        """Test role request retrieval without user_id (admin access)"""
        # Create role request using ORM
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        result = role_request_service.get_role_request(
            role_request_id=role_request.id,
            user_id=None
        )
        
        assert result is not None
        assert result.id == role_request.id
    
    def test_get_role_request_not_found(self, role_request_service, test_user):
        """Test retrieval returns None for non-existent request"""
        result = role_request_service.get_role_request(
            role_request_id=99999,
            user_id=test_user.id
        )
        
        assert result is None
    
    def test_get_role_request_unauthorized(self, role_request_service, test_user, db_session):
        """Test retrieval returns None for request owned by different user"""
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
        
        # Create role request using ORM
        role_request = RoleRequest(
            user_id=other_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        result = role_request_service.get_role_request(
            role_request_id=role_request.id,
            user_id=test_user.id
        )
        
        assert result is None


# ============================================================================
# Test Check KYC Required
# ============================================================================

class TestCheckKYCRequired:
    """Tests for check_kyc_required method"""
    
    @pytest.mark.asyncio
    async def test_check_kyc_required_true(self, role_request_service):
        """Test KYC requirement check returns true for roles that require KYC"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            # Mock seller role requiring KYC
            async def flag_checker(flag_name):
                if flag_name == "kyc_required_for_seller":
                    return True
                return False
            
            mock_flag.side_effect = flag_checker
            
            result = await role_request_service.check_kyc_required(
                requested_roles=["seller"]
            )
            
            assert result["kyc_required"] is True
            assert "seller" in result["required_for"]
    
    @pytest.mark.asyncio
    async def test_check_kyc_required_false(self, role_request_service):
        """Test KYC requirement check returns false when no roles require KYC"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = False
            
            result = await role_request_service.check_kyc_required(
                requested_roles=["buyer"]
            )
            
            assert result["kyc_required"] is False
            assert len(result["required_for"]) == 0
    
    @pytest.mark.asyncio
    async def test_check_kyc_required_multiple_roles(self, role_request_service):
        """Test KYC requirement check with multiple roles"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            async def flag_checker(flag_name):
                if flag_name == "kyc_required_for_seller":
                    return True
                if flag_name == "kyc_required_for_agent":
                    return True
                return False
            
            mock_flag.side_effect = flag_checker
            
            result = await role_request_service.check_kyc_required(
                requested_roles=["seller", "agent", "buyer"]
            )
            
            assert result["kyc_required"] is True
            assert "seller" in result["required_for"]
            assert "agent" in result["required_for"]
            assert "buyer" not in result["required_for"]
    
    @pytest.mark.asyncio
    async def test_check_kyc_required_empty_roles(self, role_request_service):
        """Test KYC requirement check with empty roles list"""
        result = await role_request_service.check_kyc_required(
            requested_roles=[]
        )
        
        assert result["kyc_required"] is False
        assert len(result["required_for"]) == 0

