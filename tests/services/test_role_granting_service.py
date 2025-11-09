"""
Enterprise-Grade Role Granting Service Tests

Comprehensive test suite for RoleGrantingService covering:
- Role granting with validation
- Skipping already assigned roles
- Skipping non-existent roles
- Role request approval workflow
- Role request rejection workflow
- Notification integration
- Audit logging integration
- Error handling and edge cases
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException, status
from datetime import datetime

from app.services.role_granting_service import RoleGrantingService
from app.models.role_request import RoleRequest, RoleRequestStatus
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.user import User
from app.services.audit_service import audit_service
from app.services.notification_service import notification_service


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(scope="function", autouse=True)
def setup_role_granting_tables(db_session):
    """
    Create tables needed for role granting tests.
    
    Uses ORM model creation - custom ArrayType and JSONBType handle
    SQLite compatibility automatically.
    """
    # Create User table first
    User.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create Role table
    Role.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create UserRole table
    UserRole.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create RoleRequest table
    RoleRequest.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create AuditLog table
    from app.models.audit_log import AuditLog
    AuditLog.__table__.create(bind=db_session.bind, checkfirst=True)
    
    yield
    
    # Clean up
    try:
        AuditLog.__table__.drop(bind=db_session.bind, checkfirst=True)
        RoleRequest.__table__.drop(bind=db_session.bind, checkfirst=True)
        UserRole.__table__.drop(bind=db_session.bind, checkfirst=True)
        Role.__table__.drop(bind=db_session.bind, checkfirst=True)
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
def test_admin(db_session):
    """Create a test admin user"""
    admin = User(
        email="admin@example.com",
        username="admin",
        first_name="Admin",
        last_name="User",
        hashed_password="hashed_password"
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.fixture
def test_roles(db_session):
    """Create test roles"""
    roles_data = [
        ("buyer", "Can browse and apply for properties"),
        ("seller", "Can list properties for sale"),
        ("agent", "Real estate professional"),
        ("landlord", "Can rent out properties"),
    ]
    
    roles = []
    for name, description in roles_data:
        role = Role(name=name, description=description)
        db_session.add(role)
        roles.append(role)
    
    db_session.commit()
    for role in roles:
        db_session.refresh(role)
    return roles


@pytest.fixture
def role_granting_service(db_session):
    """Create RoleGrantingService instance"""
    return RoleGrantingService(db_session)


# ============================================================================
# Test Grant Roles
# ============================================================================

class TestGrantRoles:
    """Tests for grant_roles method"""
    
    def test_grant_roles_success(self, role_granting_service, test_user, test_roles, db_session):
        """Test successful role granting"""
        with patch.object(audit_service, 'log_action') as mock_audit:
            result = role_granting_service.grant_roles(
                user_id=test_user.id,
                role_names=["seller", "agent"],
                granted_by=999,
                request_id="req-123"
            )
            
            assert len(result["granted_roles"]) == 2
            assert "seller" in result["granted_roles"]
            assert "agent" in result["granted_roles"]
            assert len(result["skipped_roles"]) == 0
            
            # Verify roles were actually assigned
            user_roles = db_session.query(UserRole).filter(
                UserRole.user_id == test_user.id
            ).all()
            role_ids = {ur.role_id for ur in user_roles}
            seller_role = next(r for r in test_roles if r.name == "seller")
            agent_role = next(r for r in test_roles if r.name == "agent")
            assert seller_role.id in role_ids
            assert agent_role.id in role_ids
            
            # Verify audit log
            mock_audit.assert_called_once()
            call_args = mock_audit.call_args
            assert call_args[1]["action"] == "role_granted"
            assert call_args[1]["actor_id"] == 999
            assert call_args[1]["target_type"] == "user"
            assert call_args[1]["target_id"] == test_user.id
    
    def test_grant_roles_auto_granted(self, role_granting_service, test_user, test_roles, db_session):
        """Test role granting without granted_by (auto-granted)"""
        with patch.object(audit_service, 'log_action') as mock_audit:
            result = role_granting_service.grant_roles(
                user_id=test_user.id,
                role_names=["buyer"],
                granted_by=None
            )
            
            assert len(result["granted_roles"]) == 1
            assert "buyer" in result["granted_roles"]
            
            # Verify audit log uses "role_auto_granted"
            mock_audit.assert_called_once()
            call_args = mock_audit.call_args
            assert call_args[1]["action"] == "role_auto_granted"
            assert call_args[1]["actor_id"] is None
    
    def test_grant_roles_skip_already_assigned(self, role_granting_service, test_user, test_roles, db_session):
        """Test that already assigned roles are skipped"""
        # Assign a role first
        seller_role = next(r for r in test_roles if r.name == "seller")
        user_role = UserRole(user_id=test_user.id, role_id=seller_role.id)
        db_session.add(user_role)
        db_session.commit()
        
        # Try to grant same role again
        result = role_granting_service.grant_roles(
            user_id=test_user.id,
            role_names=["seller", "agent"]
        )
        
        assert len(result["granted_roles"]) == 1
        assert "agent" in result["granted_roles"]
        assert len(result["skipped_roles"]) == 1
        assert result["skipped_roles"][0]["role"] == "seller"
        assert result["skipped_roles"][0]["reason"] == "Already assigned"
    
    def test_grant_roles_skip_nonexistent_role(self, role_granting_service, test_user, test_roles):
        """Test that non-existent roles are skipped"""
        result = role_granting_service.grant_roles(
            user_id=test_user.id,
            role_names=["nonexistent_role", "seller"]
        )
        
        assert len(result["granted_roles"]) == 1
        assert "seller" in result["granted_roles"]
        assert len(result["skipped_roles"]) == 1
        assert result["skipped_roles"][0]["role"] == "nonexistent_role"
        assert result["skipped_roles"][0]["reason"] == "Role does not exist"
    
    def test_grant_roles_updates_role_request_status(self, role_granting_service, test_user, test_roles, db_session):
        """Test that role request status is updated when role_request_id is provided"""
        # Create a role request
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        # Grant roles with role_request_id
        result = role_granting_service.grant_roles(
            user_id=test_user.id,
            role_names=["seller"],
            role_request_id=role_request.id,
            granted_by=999
        )
        
        # Verify role request was updated
        db_session.refresh(role_request)
        assert role_request.status == RoleRequestStatus.APPROVED
        assert role_request.reviewed_by == 999
        assert role_request.reviewed_at is not None
    
    def test_grant_roles_partial_success(self, role_granting_service, test_user, test_roles, db_session):
        """Test granting multiple roles with some failures"""
        # Assign one role first
        seller_role = next(r for r in test_roles if r.name == "seller")
        user_role = UserRole(user_id=test_user.id, role_id=seller_role.id)
        db_session.add(user_role)
        db_session.commit()
        
        # Try to grant: already assigned, valid new role, non-existent role
        result = role_granting_service.grant_roles(
            user_id=test_user.id,
            role_names=["seller", "agent", "nonexistent"]
        )
        
        assert len(result["granted_roles"]) == 1
        assert "agent" in result["granted_roles"]
        assert len(result["skipped_roles"]) == 2
        skipped_role_names = {s["role"] for s in result["skipped_roles"]}
        assert "seller" in skipped_role_names
        assert "nonexistent" in skipped_role_names


# ============================================================================
# Test Reject Role Request
# ============================================================================

class TestRejectRoleRequest:
    """Tests for reject_role_request method"""
    
    def test_reject_role_request_success(self, role_granting_service, test_user, test_admin, db_session):
        """Test successful role request rejection"""
        # Create a role request
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller", "agent"],
            status=RoleRequestStatus.PENDING,
            notes="Original notes"
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        with patch.object(audit_service, 'log_admin_action') as mock_audit, \
             patch.object(notification_service, 'send_role_rejection_notification', return_value=True) as mock_notify:
            
            result = role_granting_service.reject_role_request(
                role_request_id=role_request.id,
                rejected_by=test_admin.id,
                reason="Insufficient documentation",
                request_id="req-123"
            )
            
            assert result.status == RoleRequestStatus.REJECTED
            assert result.reviewed_by == test_admin.id
            assert result.reviewed_at is not None
            assert result.notes == "Insufficient documentation"
            
            # Verify audit log
            mock_audit.assert_called_once()
            call_args = mock_audit.call_args
            assert call_args[1]["action"] == "role_request_rejected"
            assert call_args[1]["admin_id"] == test_admin.id
            assert call_args[1]["target_type"] == "role_request"
            assert call_args[1]["target_id"] == role_request.id
            
            # Verify notification was sent
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args[1]  # Keyword arguments
            assert call_kwargs["to_email"] == test_user.email
            assert call_kwargs["rejected_roles"] == ["seller", "agent"]
            assert call_kwargs["reason"] == "Insufficient documentation"
    
    def test_reject_role_request_no_reason(self, role_granting_service, test_user, test_admin, db_session):
        """Test role request rejection without reason"""
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING,
            notes="Original notes"
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        with patch.object(notification_service, 'send_role_rejection_notification', return_value=True):
            result = role_granting_service.reject_role_request(
                role_request_id=role_request.id,
                rejected_by=test_admin.id,
                reason=None
            )
            
            assert result.status == RoleRequestStatus.REJECTED
            # Notes should remain unchanged if no reason provided
            assert result.notes == "Original notes"
    
    def test_reject_role_request_not_found(self, role_granting_service, test_admin):
        """Test rejection fails for non-existent role request"""
        with pytest.raises(HTTPException) as exc_info:
            role_granting_service.reject_role_request(
                role_request_id=99999,
                rejected_by=test_admin.id
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail.lower()
    
    def test_reject_role_request_notification_failure_does_not_fail(self, role_granting_service, test_user, test_admin, db_session):
        """Test that notification failure doesn't fail the rejection"""
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        with patch.object(notification_service, 'send_role_rejection_notification', return_value=False):
            # Should still succeed even if notification fails
            result = role_granting_service.reject_role_request(
                role_request_id=role_request.id,
                rejected_by=test_admin.id
            )
            
            assert result.status == RoleRequestStatus.REJECTED


# ============================================================================
# Test Approve Role Request
# ============================================================================

class TestApproveRoleRequest:
    """Tests for approve_role_request method"""
    
    def test_approve_role_request_success(self, role_granting_service, test_user, test_admin, test_roles, db_session):
        """Test successful role request approval"""
        # Create a role request
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller", "agent"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        with patch.object(audit_service, 'log_action') as mock_audit, \
             patch.object(notification_service, 'send_role_approval_notification', return_value=True) as mock_notify:
            
            result = role_granting_service.approve_role_request(
                role_request_id=role_request.id,
                approved_by=test_admin.id,
                request_id="req-123"
            )
            
            assert result.status == RoleRequestStatus.APPROVED
            assert result.reviewed_by == test_admin.id
            assert result.reviewed_at is not None
            
            # Verify roles were granted
            user_roles = db_session.query(UserRole).filter(
                UserRole.user_id == test_user.id
            ).all()
            role_ids = {ur.role_id for ur in user_roles}
            seller_role = next(r for r in test_roles if r.name == "seller")
            agent_role = next(r for r in test_roles if r.name == "agent")
            assert seller_role.id in role_ids
            assert agent_role.id in role_ids
            
            # Verify notification was sent
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args[1]  # Keyword arguments
            assert call_kwargs["to_email"] == test_user.email
            assert call_kwargs["approved_roles"] == ["seller", "agent"]
    
    def test_approve_role_request_not_found(self, role_granting_service, test_admin):
        """Test approval fails for non-existent role request"""
        with pytest.raises(HTTPException) as exc_info:
            role_granting_service.approve_role_request(
                role_request_id=99999,
                approved_by=test_admin.id
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail.lower()
    
    def test_approve_role_request_with_partial_skips(self, role_granting_service, test_user, test_admin, test_roles, db_session):
        """Test approval when some roles are skipped (already assigned or non-existent)"""
        # Assign one role first
        seller_role = next(r for r in test_roles if r.name == "seller")
        user_role = UserRole(user_id=test_user.id, role_id=seller_role.id)
        db_session.add(user_role)
        db_session.commit()
        
        # Create role request with already assigned role and non-existent role
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller", "nonexistent", "agent"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        with patch.object(notification_service, 'send_role_approval_notification', return_value=True) as mock_notify:
            result = role_granting_service.approve_role_request(
                role_request_id=role_request.id,
                approved_by=test_admin.id
            )
            
            assert result.status == RoleRequestStatus.APPROVED
            
            # Only agent should be granted (seller already assigned, nonexistent doesn't exist)
            user_roles = db_session.query(UserRole).filter(
                UserRole.user_id == test_user.id
            ).all()
            role_ids = {ur.role_id for ur in user_roles}
            agent_role = next(r for r in test_roles if r.name == "agent")
            assert agent_role.id in role_ids
            
            # Notification should only include granted roles
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args[1]  # Keyword arguments
            assert call_kwargs["approved_roles"] == ["agent"]
    
    def test_approve_role_request_no_granted_roles_no_notification(self, role_granting_service, test_user, test_admin, db_session):
        """Test that notification is not sent if no roles were granted"""
        # Create role request with non-existent roles only
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["nonexistent1", "nonexistent2"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        with patch.object(notification_service, 'send_role_approval_notification') as mock_notify:
            result = role_granting_service.approve_role_request(
                role_request_id=role_request.id,
                approved_by=test_admin.id
            )
            
            assert result.status == RoleRequestStatus.APPROVED
            
            # Notification should not be sent if no roles were granted
            mock_notify.assert_not_called()
    
    def test_approve_role_request_notification_failure_does_not_fail(self, role_granting_service, test_user, test_admin, test_roles, db_session):
        """Test that notification failure doesn't fail the approval"""
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        with patch.object(notification_service, 'send_role_approval_notification', return_value=False):
            # Should still succeed even if notification fails
            result = role_granting_service.approve_role_request(
                role_request_id=role_request.id,
                approved_by=test_admin.id
            )
            
            assert result.status == RoleRequestStatus.APPROVED


# ============================================================================
# Test Integration Scenarios
# ============================================================================

class TestRoleGrantingIntegration:
    """Integration tests for role granting workflows"""
    
    def test_full_approval_workflow(self, role_granting_service, test_user, test_admin, test_roles, db_session):
        """Test complete approval workflow: request -> approve -> verify roles"""
        # Create role request
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller", "agent"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        # Approve request
        with patch.object(notification_service, 'send_role_approval_notification', return_value=True):
            approved_request = role_granting_service.approve_role_request(
                role_request_id=role_request.id,
                approved_by=test_admin.id
            )
        
        # Verify request status
        assert approved_request.status == RoleRequestStatus.APPROVED
        assert approved_request.reviewed_by == test_admin.id
        
        # Verify roles were assigned
        user_roles = db_session.query(UserRole).filter(
            UserRole.user_id == test_user.id
        ).all()
        assert len(user_roles) == 2
        role_names = {db_session.query(Role).filter(Role.id == ur.role_id).first().name for ur in user_roles}
        assert "seller" in role_names
        assert "agent" in role_names
    
    def test_full_rejection_workflow(self, role_granting_service, test_user, test_admin, db_session):
        """Test complete rejection workflow: request -> reject -> verify status"""
        # Create role request
        role_request = RoleRequest(
            user_id=test_user.id,
            requested_roles=["seller"],
            status=RoleRequestStatus.PENDING
        )
        db_session.add(role_request)
        db_session.commit()
        db_session.refresh(role_request)
        
        # Reject request
        with patch.object(notification_service, 'send_role_rejection_notification', return_value=True):
            rejected_request = role_granting_service.reject_role_request(
                role_request_id=role_request.id,
                rejected_by=test_admin.id,
                reason="Insufficient documentation"
            )
        
        # Verify request status
        assert rejected_request.status == RoleRequestStatus.REJECTED
        assert rejected_request.reviewed_by == test_admin.id
        assert rejected_request.notes == "Insufficient documentation"
        
        # Verify no roles were assigned
        user_roles = db_session.query(UserRole).filter(
            UserRole.user_id == test_user.id
        ).all()
        assert len(user_roles) == 0

