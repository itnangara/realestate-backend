"""
Integration tests for role request workflow

Tests end-to-end role request flow:
- Submit request → View requests → Admin approve/reject
- Feature flag disabled scenario
- Invalid roles validation
- Document attachment validation
- KYC requirement checking
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi import status

from app.models.role_request import RoleRequest, RoleRequestStatus
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.core.feature_flags import feature_flags


@pytest.fixture(scope="function", autouse=True)
def setup_role_request_tables(db_session):
    """
    Create tables needed for role request workflow tests.
    
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
    
    yield
    
    # Clean up
    try:
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
def test_admin_user(db_session, auth_service, test_roles):
    """Create test admin user"""
    hashed_password = auth_service.get_password_hash("adminpass123")
    admin = User(
        email="admin@test.com",
        username="adminuser",
        first_name="Admin",
        last_name="User",
        hashed_password=hashed_password
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    
    # Assign admin role
    admin_role = db_session.query(Role).filter_by(name="admin").first()
    user_role = UserRole(user_id=admin.id, role_id=admin_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return admin


@pytest.fixture
def user_token(client, test_user_with_roles):
    """Get user authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "user@test.com",
        "password": "testpass123"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def admin_token(client, test_admin_user):
    """Get admin authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "admin@test.com",
        "password": "adminpass123"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def user_headers(user_token):
    """User authentication headers"""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token):
    """Admin authentication headers"""
    return {"Authorization": f"Bearer {admin_token}"}


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
            type=DocumentType.COMPANY_DOC,
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


class TestRoleRequestWorkflow:
    """Tests for complete role request workflow"""
    
    @pytest.mark.asyncio
    async def test_submit_role_request_with_documents(self, client, user_headers, db_session, test_user_with_roles, test_documents):
        """Test submitting a role request with attached documents"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = True
            
            request_data = {
                "requested_roles": ["seller", "agent"],
                "document_ids": [doc.id for doc in test_documents],
                "notes": "I want to sell properties"
            }
            
            response = client.post(
                "/api/roles/request",
                json=request_data,
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_201_CREATED
            role_request = response.json()
            assert role_request["status"] == RoleRequestStatus.PENDING.value
            assert set(role_request["requested_roles"]) == {"seller", "agent"}
            assert role_request["attachments"] == [doc.id for doc in test_documents]
            assert role_request["user_id"] == test_user_with_roles.id
            
            # Verify in database
            db_request = db_session.query(RoleRequest).filter_by(id=role_request["id"]).first()
            assert db_request is not None
            assert db_request.status == RoleRequestStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_submit_role_request_without_documents(self, client, user_headers):
        """Test submitting a role request without documents"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = True
            
            request_data = {
                "requested_roles": ["seller"],
                "notes": "I want to sell properties"
            }
            
            response = client.post(
                "/api/roles/request",
                json=request_data,
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_201_CREATED
            role_request = response.json()
            assert role_request["status"] == RoleRequestStatus.PENDING.value
            assert role_request["requested_roles"] == ["seller"]
    
    @pytest.mark.asyncio
    async def test_submit_role_request_feature_flag_disabled(self, client, user_headers):
        """Test role request fails when feature flag is disabled"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = False
            
            request_data = {
                "requested_roles": ["seller"],
                "notes": "I want to sell properties"
            }
            
            response = client.post(
                "/api/roles/request",
                json=request_data,
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "disabled" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_submit_role_request_invalid_roles(self, client, user_headers):
        """Test role request fails with invalid roles"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = True
            
            # Try to request buyer role (not allowed)
            request_data = {
                "requested_roles": ["buyer"],
                "notes": "Invalid request"
            }
            
            response = client.post(
                "/api/roles/request",
                json=request_data,
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
            
            # Try to request admin role (not allowed)
            request_data = {
                "requested_roles": ["admin"],
                "notes": "Invalid request"
            }
            
            response = client.post(
                "/api/roles/request",
                json=request_data,
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @pytest.mark.asyncio
    async def test_submit_role_request_invalid_documents(self, client, user_headers, db_session, test_user_with_roles):
        """Test role request fails with documents that don't belong to user"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = True
            
            # Create another user with a document
            from app.services.auth_service import AuthService
            auth_service = AuthService(db_session)
            hashed_password = auth_service.get_password_hash("otherpass")
            other_user = User(
                email="other@test.com",
                username="otheruser",
                first_name="Other",
                last_name="User",
                hashed_password=hashed_password
            )
            db_session.add(other_user)
            db_session.commit()
            db_session.refresh(other_user)
            
            other_doc = Document(
                user_id=other_user.id,
                type=DocumentType.ID_FRONT,
                s3_key="other-doc.pdf",
                status=DocumentStatus.UPLOADED
            )
            db_session.add(other_doc)
            db_session.commit()
            db_session.refresh(other_doc)
            
            # Try to use other user's document
            request_data = {
                "requested_roles": ["seller"],
                "document_ids": [other_doc.id],
                "notes": "Invalid request"
            }
            
            response = client.post(
                "/api/roles/request",
                json=request_data,
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "document" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_get_user_role_requests(self, client, user_headers, db_session, test_user_with_roles):
        """Test retrieving user's role requests"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = True
            
            # Create multiple role requests
            requests = [
                RoleRequest(
                    user_id=test_user_with_roles.id,
                    requested_roles=["seller"],
                    status=RoleRequestStatus.PENDING
                ),
                RoleRequest(
                    user_id=test_user_with_roles.id,
                    requested_roles=["agent"],
                    status=RoleRequestStatus.IN_REVIEW
                )
            ]
            for req in requests:
                db_session.add(req)
            db_session.commit()
            
            # Get all requests
            response = client.get(
                "/api/roles/requests/me",
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_200_OK
            list_response = response.json()
            assert list_response["total"] >= 2
            
            # Filter by status
            response = client.get(
                "/api/roles/requests/me?status=pending",
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_200_OK
            list_response = response.json()
            assert all(req["status"] == RoleRequestStatus.PENDING.value for req in list_response["requests"])
    
    @pytest.mark.asyncio
    async def test_admin_list_role_requests(self, client, admin_headers, db_session, test_user_with_roles):
        """Test admin listing role requests with filters"""
        # Create role requests
        requests = [
            RoleRequest(
                user_id=test_user_with_roles.id,
                requested_roles=["seller"],
                status=RoleRequestStatus.PENDING
            ),
            RoleRequest(
                user_id=test_user_with_roles.id,
                requested_roles=["agent"],
                status=RoleRequestStatus.IN_REVIEW
            )
        ]
        for req in requests:
            db_session.add(req)
        db_session.commit()
        
        # List all requests
        response = client.get(
            "/api/admin/role-requests",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert list_response["total"] >= 2
        
        # Filter by status
        response = client.get(
            "/api/admin/role-requests?status_filter=pending",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert all(req["status"] == RoleRequestStatus.PENDING.value for req in list_response["requests"])
        
        # Filter by role
        response = client.get(
            "/api/admin/role-requests?role=seller",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert any("seller" in req["requested_roles"] for req in list_response["requests"])
    
    @pytest.mark.asyncio
    async def test_admin_approve_role_request(self, client, admin_headers, db_session, test_user_with_roles):
        """Test admin approving a role request"""
        # Create role request
        role_request = RoleRequest(
            user_id=test_user_with_roles.id,
            requested_roles=["seller", "agent"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        with patch('app.services.notification_service.NotificationService.send_role_approval_notification', return_value=True):
            # Approve request
            response = client.post(
                f"/api/admin/role-requests/{role_request.id}/approve",
                headers=admin_headers
            )
            
            assert response.status_code == status.HTTP_200_OK
            approved_request = response.json()
            assert approved_request["status"] == RoleRequestStatus.APPROVED.value
            
            # Verify roles were granted
            db_session.refresh(role_request)
            assert role_request.status == RoleRequestStatus.APPROVED
            
            # Verify user has the roles
            user_roles = db_session.query(UserRole).join(Role).filter(
                UserRole.user_id == test_user_with_roles.id
            ).all()
            role_names = {db_session.query(Role).filter_by(id=ur.role_id).first().name for ur in user_roles}
            assert "seller" in role_names
            assert "agent" in role_names
    
    @pytest.mark.asyncio
    async def test_admin_reject_role_request(self, client, admin_headers, db_session, test_user_with_roles):
        """Test admin rejecting a role request"""
        # Create role request
        role_request = RoleRequest(
            user_id=test_user_with_roles.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        with patch('app.services.notification_service.NotificationService.send_role_rejection_notification', return_value=True):
            # Reject request
            response = client.post(
                f"/api/admin/role-requests/{role_request.id}/reject?reason=Insufficient%20documentation",
                headers=admin_headers
            )
            
            assert response.status_code == status.HTTP_200_OK
            rejected_request = response.json()
            assert rejected_request["status"] == RoleRequestStatus.REJECTED.value
            
            # Verify in database
            db_session.refresh(role_request)
            assert role_request.status == RoleRequestStatus.REJECTED
    
    @pytest.mark.asyncio
    async def test_admin_access_required(self, client, user_headers, db_session, test_user_with_roles):
        """Test that non-admin users cannot access admin endpoints"""
        # Create role request
        role_request = RoleRequest(
            user_id=test_user_with_roles.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        # Try to access admin endpoints as regular user
        response = client.get(
            "/api/admin/role-requests",
            headers=user_headers
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        response = client.post(
            f"/api/admin/role-requests/{role_request.id}/approve",
            headers=user_headers
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

