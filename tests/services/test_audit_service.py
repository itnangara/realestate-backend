"""
Audit Service Tests

Tests:
- Log user action → assert audit_logs entry is created
- Log admin action → assert audit_logs entry is created
- Log system action → assert audit_logs entry is created
- Verify actor_id, action, target_type, target_id, meta
- Test request ID correlation
"""

import pytest
from sqlalchemy.orm import Session
from sqlalchemy import Table, Column, Integer, String, DateTime, ForeignKey, Index, JSON, text
from sqlalchemy.sql import func

from app.services.audit_service import AuditService, audit_service
from app.models.audit_log import AuditLog
from app.models.user import User
from app.utils.database import Base


@pytest.fixture(scope="function", autouse=True)
def setup_audit_tables(db_session):
    """
    Create only the tables needed for audit tests (User and AuditLog).
    This avoids issues with PostgreSQL-specific types (ARRAY, JSONB) in SQLite.
    For SQLite, we create a compatible version of the audit_logs table using JSON instead of JSONB.
    """
    # Create User table first (AuditLog has FK to it)
    User.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # For SQLite compatibility, create audit_logs table with JSON instead of JSONB
    # Use raw SQL to create a SQLite-compatible version
    from sqlalchemy import inspect as sqlalchemy_inspect
    inspector = sqlalchemy_inspect(db_session.bind)
    if 'audit_logs' not in inspector.get_table_names():
        # Create table with SQLite-compatible SQL (JSON instead of JSONB)
        create_table_sql = """
        CREATE TABLE audit_logs (
            id INTEGER NOT NULL PRIMARY KEY,
            actor_id INTEGER,
            action VARCHAR(255) NOT NULL,
            target_type VARCHAR(50),
            target_id INTEGER,
            meta JSON,
            request_id VARCHAR(255),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(actor_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
        db_session.execute(text(create_table_sql))
        # Create indexes
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_id ON audit_logs(actor_id)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs(action)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_target_type ON audit_logs(target_type)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_target_id ON audit_logs(target_id)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_request_id ON audit_logs(request_id)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs(created_at)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_action ON audit_logs(actor_id, action)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_target ON audit_logs(target_type, target_id)"))
        db_session.commit()
    
    yield
    
    # Clean up
    try:
        db_session.execute(text("DROP TABLE IF EXISTS audit_logs"))
        db_session.commit()
    except Exception:
        pass
    try:
        User.__table__.drop(bind=db_session.bind, checkfirst=True)
    except Exception:
        pass


class TestLogUserAction:
    """Tests for logging user actions"""
    
    def test_log_user_action_creates_entry(self, db_session):
        """Test that log_user_action creates an audit log entry"""
        action = "role_request_created"
        user_id = 123
        target_type = "role_request"
        target_id = 456
        meta = {"requested_roles": ["seller", "agent"]}
        request_id = "req-123-456"
        
        audit_log = audit_service.log_user_action(
            db=db_session,
            action=action,
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
            meta=meta,
            request_id=request_id
        )
        
        assert audit_log is not None
        assert audit_log.id is not None
        assert audit_log.actor_id == user_id
        assert audit_log.action == action
        assert audit_log.target_type == target_type
        assert audit_log.target_id == target_id
        assert audit_log.meta == meta
        assert audit_log.request_id == request_id
        assert audit_log.created_at is not None
    
    def test_log_user_action_verifies_actor_id(self, db_session):
        """Test that actor_id is correctly set for user actions"""
        user_id = 789
        
        audit_log = audit_service.log_user_action(
            db=db_session,
            action="document_uploaded",
            user_id=user_id
        )
        
        assert audit_log.actor_id == user_id
    
    def test_log_user_action_minimal_fields(self, db_session):
        """Test logging with minimal required fields"""
        audit_log = audit_service.log_user_action(
            db=db_session,
            action="test_action",
            user_id=111
        )
        
        assert audit_log is not None
        assert audit_log.actor_id == 111
        assert audit_log.action == "test_action"
        assert audit_log.target_type is None
        assert audit_log.target_id is None
        assert audit_log.meta is None
        assert audit_log.request_id is None


class TestLogAdminAction:
    """Tests for logging admin actions"""
    
    def test_log_admin_action_creates_entry(self, db_session):
        """Test that log_admin_action creates an audit log entry"""
        action = "role_request_approved"
        admin_id = 999
        target_type = "role_request"
        target_id = 456
        meta = {"approved_roles": ["seller"], "notes": "Approved"}
        request_id = "req-admin-789"
        
        audit_log = audit_service.log_admin_action(
            db=db_session,
            action=action,
            admin_id=admin_id,
            target_type=target_type,
            target_id=target_id,
            meta=meta,
            request_id=request_id
        )
        
        assert audit_log is not None
        assert audit_log.id is not None
        assert audit_log.actor_id == admin_id
        assert audit_log.action == action
        assert audit_log.target_type == target_type
        assert audit_log.target_id == target_id
        assert audit_log.meta == meta
        assert audit_log.request_id == request_id
    
    def test_log_admin_action_verifies_actor_id(self, db_session):
        """Test that actor_id is correctly set for admin actions"""
        admin_id = 888
        
        audit_log = audit_service.log_admin_action(
            db=db_session,
            action="user_suspended",
            admin_id=admin_id
        )
        
        assert audit_log.actor_id == admin_id


class TestLogSystemAction:
    """Tests for logging system actions"""
    
    def test_log_system_action_creates_entry(self, db_session):
        """Test that log_system_action creates an audit log entry"""
        action = "kyc_webhook_received"
        target_type = "kyc_request"
        target_id = 777
        meta = {"provider": "sumsub", "status": "approved"}
        request_id = "webhook-123"
        
        audit_log = audit_service.log_system_action(
            db=db_session,
            action=action,
            target_type=target_type,
            target_id=target_id,
            meta=meta,
            request_id=request_id
        )
        
        assert audit_log is not None
        assert audit_log.id is not None
        assert audit_log.actor_id is None  # System actions have no actor
        assert audit_log.action == action
        assert audit_log.target_type == target_type
        assert audit_log.target_id == target_id
        assert audit_log.meta == meta
        assert audit_log.request_id == request_id
    
    def test_log_system_action_no_actor(self, db_session):
        """Test that system actions have no actor_id"""
        audit_log = audit_service.log_system_action(
            db=db_session,
            action="auto_role_granted"
        )
        
        assert audit_log.actor_id is None


class TestLogActionGeneric:
    """Tests for generic log_action method"""
    
    def test_log_action_with_all_fields(self, db_session):
        """Test log_action with all fields populated"""
        action = "custom_action"
        actor_id = 555
        target_type = "custom_target"
        target_id = 444
        meta = {
            "field1": "value1",
            "field2": 123,
            "nested": {"key": "value"}
        }
        request_id = "req-custom-123"
        
        audit_log = audit_service.log_action(
            db=db_session,
            action=action,
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            meta=meta,
            request_id=request_id
        )
        
        assert audit_log.actor_id == actor_id
        assert audit_log.action == action
        assert audit_log.target_type == target_type
        assert audit_log.target_id == target_id
        assert audit_log.meta == meta
        assert audit_log.request_id == request_id
    
    def test_log_action_verifies_meta_jsonb(self, db_session):
        """Test that meta field stores complex JSON structures"""
        complex_meta = {
            "user_email": "test@example.com",
            "roles": ["seller", "agent"],
            "status_changes": [
                {"from": "pending", "to": "approved", "at": "2025-01-01T00:00:00Z"}
            ],
            "numbers": [1, 2, 3],
            "nested": {
                "level1": {
                    "level2": "deep_value"
                }
            }
        }
        
        audit_log = audit_service.log_action(
            db=db_session,
            action="complex_action",
            actor_id=111,
            meta=complex_meta
        )
        
        assert audit_log.meta == complex_meta
        assert audit_log.meta["user_email"] == "test@example.com"
        assert audit_log.meta["roles"] == ["seller", "agent"]
        assert len(audit_log.meta["status_changes"]) == 1


class TestRequestIDCorrelation:
    """Tests for request ID correlation"""
    
    def test_request_id_correlation_same_request(self, db_session):
        """Test that multiple actions with same request_id can be correlated"""
        request_id = "req-correlation-123"
        
        log1 = audit_service.log_user_action(
            db=db_session,
            action="action_1",
            user_id=111,
            request_id=request_id
        )
        
        log2 = audit_service.log_user_action(
            db=db_session,
            action="action_2",
            user_id=111,
            request_id=request_id
        )
        
        # Both should have the same request_id
        assert log1.request_id == request_id
        assert log2.request_id == request_id
        
        # Query by request_id to verify correlation
        logs = db_session.query(AuditLog).filter(
            AuditLog.request_id == request_id
        ).all()
        
        assert len(logs) == 2
        assert all(log.request_id == request_id for log in logs)
    
    def test_request_id_correlation_different_requests(self, db_session):
        """Test that different request_ids are not correlated"""
        request_id_1 = "req-1"
        request_id_2 = "req-2"
        
        audit_service.log_user_action(
            db=db_session,
            action="action_1",
            user_id=111,
            request_id=request_id_1
        )
        
        audit_service.log_user_action(
            db=db_session,
            action="action_2",
            user_id=222,
            request_id=request_id_2
        )
        
        # Query by first request_id
        logs_1 = db_session.query(AuditLog).filter(
            AuditLog.request_id == request_id_1
        ).all()
        
        assert len(logs_1) == 1
        assert logs_1[0].request_id == request_id_1


class TestAuditLogPersistence:
    """Tests for audit log persistence and retrieval"""
    
    def test_audit_log_persisted_to_database(self, db_session):
        """Test that audit log is actually persisted to database"""
        # Table is already created by setup_audit_tables fixture
        audit_log = audit_service.log_user_action(
            db=db_session,
            action="test_persistence",
            user_id=123
        )
        
        audit_log_id = audit_log.id
        
        # Verify it's in the same session
        retrieved_log = db_session.query(AuditLog).filter(
            AuditLog.id == audit_log_id
        ).first()
        
        assert retrieved_log is not None
        assert retrieved_log.id == audit_log_id
        assert retrieved_log.action == "test_persistence"
        assert retrieved_log.actor_id == 123
    
    def test_multiple_audit_logs_created(self, db_session):
        """Test that multiple audit logs can be created"""
        actions = [
            ("action_1", 111),
            ("action_2", 222),
            ("action_3", 333),
        ]
        
        created_logs = []
        for action, user_id in actions:
            log = audit_service.log_user_action(
                db=db_session,
                action=action,
                user_id=user_id
            )
            created_logs.append(log)
        
        # Verify all were created
        assert len(created_logs) == 3
        
        # Verify all have unique IDs
        ids = [log.id for log in created_logs]
        assert len(set(ids)) == 3
        
        # Verify all are in database
        all_logs = db_session.query(AuditLog).all()
        assert len(all_logs) >= 3

