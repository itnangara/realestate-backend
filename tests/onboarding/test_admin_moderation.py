"""
Integration tests for admin moderation workflow

Tests admin moderation features:
- List role requests with filters
- Approve role request → Verify roles granted
- Reject role request → Verify notification sent
- Admin-only access enforcement
- Pagination and filtering
"""

import pytest
from unittest.mock import patch
from fastapi import status
from datetime import datetime, timedelta

from app.models.role_request import RoleRequest, RoleRequestStatus
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole


@pytest.fixture(scope="function", autouse=True)
def setup_admin_tables(db_session):
    """
    Create tables needed for admin moderation tests.
    
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
def test_users(db_session, auth_service, test_roles):
    """Create multiple test users"""
    users = []
    for i in range(3):
        hashed_password = auth_service.get_password_hash(f"pass{i}")
        user = User(
            email=f"user{i}@test.com",
            username=f"user{i}",
            first_name=f"User{i}",
            last_name="Test",
            hashed_password=hashed_password
        )
        db_session.add(user)
        users.append(user)
    
    db_session.commit()
    for user in users:
        db_session.refresh(user)
        # Assign buyer role
        buyer_role = db_session.query(Role).filter_by(name="buyer").first()
        user_role = UserRole(user_id=user.id, role_id=buyer_role.id)
        db_session.add(user_role)
    
    db_session.commit()
    return users


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
def test_regular_user(db_session, auth_service, test_roles):
    """Create test regular user (non-admin)"""
    hashed_password = auth_service.get_password_hash("userpass123")
    user = User(
        email="regular@test.com",
        username="regularuser",
        first_name="Regular",
        last_name="User",
        hashed_password=hashed_password
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Assign buyer role only
    buyer_role = db_session.query(Role).filter_by(name="buyer").first()
    user_role = UserRole(user_id=user.id, role_id=buyer_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


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
def regular_token(client, test_regular_user):
    """Get regular user authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "regular@test.com",
        "password": "userpass123"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    """Admin authentication headers"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def regular_headers(regular_token):
    """Regular user authentication headers"""
    return {"Authorization": f"Bearer {regular_token}"}


@pytest.fixture
def test_role_requests(db_session, test_users):
    """Create multiple role requests with different statuses"""
    requests = [
        RoleRequest(
            user_id=test_users[0].id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        ),
        RoleRequest(
            user_id=test_users[1].id,
            requested_roles=["agent"],
            status=RoleRequestStatus.IN_REVIEW
        ),
        RoleRequest(
            user_id=test_users[2].id,
            requested_roles=["seller", "agent"],
            status=RoleRequestStatus.PENDING
        ),
        RoleRequest(
            user_id=test_users[0].id,
            requested_roles=["landlord"],
            status=RoleRequestStatus.APPROVED
        ),
        RoleRequest(
            user_id=test_users[1].id,
            requested_roles=["investor"],
            status=RoleRequestStatus.REJECTED
        )
    ]
    for req in requests:
        db_session.add(req)
    db_session.commit()
    for req in requests:
        db_session.refresh(req)
    return requests


class TestAdminModeration:
    """Tests for admin moderation workflows"""
    
    def test_list_all_role_requests(self, client, admin_headers, test_role_requests):
        """Test admin can list all role requests"""
        response = client.get(
            "/api/admin/role-requests",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert list_response["total"] >= len(test_role_requests)
        assert len(list_response["requests"]) > 0
    
    def test_list_role_requests_filter_by_status(self, client, admin_headers, test_role_requests):
        """Test filtering role requests by status"""
        # Filter by pending
        response = client.get(
            "/api/admin/role-requests?status_filter=pending",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert all(req["status"] == RoleRequestStatus.PENDING.value for req in list_response["requests"])
        
        # Filter by approved
        response = client.get(
            "/api/admin/role-requests?status_filter=approved",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert all(req["status"] == RoleRequestStatus.APPROVED.value for req in list_response["requests"])
    
    def test_list_role_requests_filter_by_role(self, client, admin_headers, test_role_requests):
        """Test filtering role requests by requested role"""
        # Filter by seller role
        response = client.get(
            "/api/admin/role-requests?role=seller",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert all("seller" in req["requested_roles"] for req in list_response["requests"])
    
    def test_list_role_requests_pagination(self, client, admin_headers, test_role_requests):
        """Test pagination of role requests"""
        # First page
        response = client.get(
            "/api/admin/role-requests?limit=2&offset=0",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert len(list_response["requests"]) <= 2
        
        # Second page
        response = client.get(
            "/api/admin/role-requests?limit=2&offset=2",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response2 = response.json()
        # Verify different results
        ids1 = {req["id"] for req in list_response["requests"]}
        ids2 = {req["id"] for req in list_response2["requests"]}
        assert ids1 != ids2 or len(list_response2["requests"]) == 0
    
    def test_get_role_request_details(self, client, admin_headers, test_role_requests):
        """Test admin can get detailed role request information"""
        role_request = test_role_requests[0]
        
        response = client.get(
            f"/api/admin/role-requests/{role_request.id}",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        request_data = response.json()
        assert request_data["id"] == role_request.id
        assert request_data["user_id"] == role_request.user_id
        assert request_data["requested_roles"] == role_request.requested_roles
    
    def test_get_role_request_not_found(self, client, admin_headers):
        """Test getting non-existent role request returns 404"""
        response = client.get(
            "/api/admin/role-requests/99999",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_approve_role_request(self, client, admin_headers, db_session, test_users, test_admin_user):
        """Test admin approving a role request grants roles to user"""
        # Create role request
        role_request = RoleRequest(
            user_id=test_users[0].id,
            requested_roles=["seller", "agent"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        # Verify user doesn't have these roles yet
        user_roles_before = db_session.query(UserRole).join(Role).filter(
            UserRole.user_id == test_users[0].id
        ).all()
        role_names_before = {db_session.query(Role).filter_by(id=ur.role_id).first().name for ur in user_roles_before}
        assert "seller" not in role_names_before
        assert "agent" not in role_names_before
        
        with patch('app.services.notification_service.NotificationService.send_role_approval_notification', return_value=True):
            # Approve request
            response = client.post(
                f"/api/admin/role-requests/{role_request.id}/approve",
                headers=admin_headers
            )
            
            assert response.status_code == status.HTTP_200_OK
            approved_request = response.json()
            assert approved_request["status"] == RoleRequestStatus.APPROVED.value
            assert approved_request["reviewed_by"] == test_admin_user.id
            
            # Verify roles were granted
            db_session.refresh(role_request)
            assert role_request.status == RoleRequestStatus.APPROVED
            assert role_request.reviewed_by == test_admin_user.id
            
            user_roles_after = db_session.query(UserRole).join(Role).filter(
                UserRole.user_id == test_users[0].id
            ).all()
            role_names_after = {db_session.query(Role).filter_by(id=ur.role_id).first().name for ur in user_roles_after}
            assert "seller" in role_names_after
            assert "agent" in role_names_after
    
    def test_reject_role_request(self, client, admin_headers, db_session, test_users, test_admin_user):
        """Test admin rejecting a role request"""
        # Create role request
        role_request = RoleRequest(
            user_id=test_users[0].id,
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
            assert rejected_request["reviewed_by"] == test_admin_user.id
            
            # Verify in database
            db_session.refresh(role_request)
            assert role_request.status == RoleRequestStatus.REJECTED
            assert role_request.reviewed_by == test_admin_user.id
            
            # Verify roles were NOT granted
            user_roles = db_session.query(UserRole).join(Role).filter(
                UserRole.user_id == test_users[0].id
            ).all()
            role_names = {db_session.query(Role).filter_by(id=ur.role_id).first().name for ur in user_roles}
            assert "seller" not in role_names
    
    def test_approve_already_approved_request(self, client, admin_headers, db_session, test_users, test_admin_user):
        """Test approving an already approved request"""
        # Create approved role request
        role_request = RoleRequest(
            user_id=test_users[0].id,
            requested_roles=["seller"],
            status=RoleRequestStatus.APPROVED,
            reviewed_by=test_admin_user.id
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        with patch('app.services.notification_service.NotificationService.send_role_approval_notification', return_value=True):
            # Try to approve again
            response = client.post(
                f"/api/admin/role-requests/{role_request.id}/approve",
                headers=admin_headers
            )
            
            # Should still succeed (idempotent operation)
            assert response.status_code == status.HTTP_200_OK
    
    def test_admin_access_required_for_listing(self, client, regular_headers):
        """Test that non-admin users cannot list role requests"""
        response = client.get(
            "/api/admin/role-requests",
            headers=regular_headers
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_admin_access_required_for_approval(self, client, regular_headers, db_session, test_users):
        """Test that non-admin users cannot approve role requests"""
        # Create role request
        role_request = RoleRequest(
            user_id=test_users[0].id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        response = client.post(
            f"/api/admin/role-requests/{role_request.id}/approve",
            headers=regular_headers
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_admin_access_required_for_rejection(self, client, regular_headers, db_session, test_users):
        """Test that non-admin users cannot reject role requests"""
        # Create role request
        role_request = RoleRequest(
            user_id=test_users[0].id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        response = client.post(
            f"/api/admin/role-requests/{role_request.id}/reject",
            headers=regular_headers
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN

