"""
Comprehensive tests for lease management flow
Tests the complete workflow: create → send → sign → counter-sign → activate
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi.testclient import TestClient

from app.models.lease import LeaseStatus, LeaseSignature
from app.models.application import ApplicationStatus
from app.models.property import PropertyStatus
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.services.auth_service import AuthService


@pytest.fixture(scope="function")
def test_user_landlord(db_session, auth_service, test_roles):
    """Create test landlord user"""
    hashed_password = auth_service.get_password_hash("landlordpassword")
    user = User(
        email="landlord@test.com",
        username="landlord_user",
        first_name="Test",
        last_name="Landlord",
        hashed_password=hashed_password,
        is_verified=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    landlord_role = db_session.query(Role).filter(Role.name == "landlord").first()
    user_role = UserRole(user_id=user.id, role_id=landlord_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


@pytest.fixture(scope="function")
def test_user_tenant(db_session, auth_service, test_roles):
    """Create test tenant user"""
    hashed_password = auth_service.get_password_hash("tenantpassword")
    user = User(
        email="tenant@test.com",
        username="tenant_user",
        first_name="Test",
        last_name="Tenant",
        hashed_password=hashed_password,
        is_verified=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    tenant_role = db_session.query(Role).filter(Role.name == "tenant").first()
    user_role = UserRole(user_id=user.id, role_id=tenant_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


@pytest.fixture(scope="function")
def auth_landlord_token(client, test_user_landlord):
    """Get landlord authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "landlord@test.com",
        "password": "landlordpassword"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="function")
def auth_tenant_token(client, test_user_tenant):
    """Get tenant authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "tenant@test.com",
        "password": "tenantpassword"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def test_property_for_lease(db_session, test_user_landlord):
    """Create a test property owned by landlord"""
    from app.models.property import Property, PropertyType, PropertyStatus, ListingType
    
    property = Property(
        title="Test Property for Lease",
        description="Property for lease testing",
        property_type=PropertyType.HOUSE,
        listing_type=ListingType.FOR_RENT,
        status=PropertyStatus.ACTIVE,
        address="123 Test Street",
        city="Test City",
        state="TS",
        zip_code="12345",
        price=1200.00,
        owner_id=test_user_landlord.id,
        is_active=True
    )
    db_session.add(property)
    db_session.commit()
    db_session.refresh(property)
    return property


@pytest.fixture
def approved_application(db_session, test_user_landlord, test_user_tenant, test_property_for_lease):
    """Create an approved application for lease creation"""
    from app.models.application import Application, ApplicationStatus
    
    app = Application(
        property_id=test_property_for_lease.id,
        applicant_id=test_user_tenant.id,
        status=ApplicationStatus.APPROVED,
        message="Test application",
        annual_income=50000,
        credit_score=700
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    return app


class TestLeaseCreation:
    """Test lease creation from approved application"""
    
    def test_create_lease_success(self, client: TestClient, auth_landlord_token, approved_application):
        """Test successful lease creation"""
        lease_data = {
            "application_id": approved_application.id,
            "rent": "1200.00",
            "deposit": "1200.00",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=395)).isoformat(),
            "terms": "Standard lease terms",
            "clauses": [{"type": "rent", "amount": 1200}]
        }
        
        response = client.post(
            "/api/leases",
            json=lease_data,
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["rent"] == 1200.0  # Enterprise-grade: rent is returned as number, not string
        assert data["application_id"] == approved_application.id
        assert data["landlord_id"] is not None
        assert data["tenant_id"] is not None
    
    def test_create_lease_requires_approved_application(self, client: TestClient, auth_landlord_token, db_session, test_user_tenant, test_property_for_lease):
        """Test that lease can only be created from APPROVED application"""
        from app.models.application import Application, ApplicationStatus
        
        from app.models.application import Application
        
        # Create SUBMITTED application
        app = Application(
            property_id=test_property_for_lease.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.SUBMITTED
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        
        lease_data = {
            "application_id": app.id,
            "rent": "1200.00",
            "deposit": "1200.00",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=395)).isoformat()
        }
        
        response = client.post(
            "/api/leases",
            json=lease_data,
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 400
        response_data = response.json()
        detail = response_data.get("detail", response_data)
        error_text = str(detail)
        if isinstance(detail, dict):
            error_text = detail.get("message", str(detail))
        assert "APPROVED" in error_text or "approved" in error_text.lower()
    
    def test_create_lease_duplicate(self, client: TestClient, auth_landlord_token, approved_application, db_session):
        """Test that duplicate lease cannot be created for same application"""
        from app.models.lease import Lease, LeaseStatus
        
        # Create first lease
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1200.00"),
            status=LeaseStatus.DRAFT
        )
        db_session.add(lease)
        db_session.commit()
        
        # Try to create duplicate
        lease_data = {
            "application_id": approved_application.id,
            "rent": "1200.00",
            "deposit": "1200.00",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=395)).isoformat()
        }
        
        response = client.post(
            "/api/leases",
            json=lease_data,
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 400
        response_data = response.json()
        # Check both possible error formats
        detail = response_data.get("detail", response_data)
        error_text = str(detail)
        if isinstance(detail, dict):
            error_text = detail.get("message", str(detail))
        assert "already exists" in error_text or "duplicate" in error_text.lower()


class TestLeaseSend:
    """Test sending lease to tenant"""
    
    def test_send_lease_success(self, client: TestClient, auth_landlord_token, approved_application, db_session):
        """Test successful lease sending"""
        from app.models.lease import Lease, LeaseStatus
        
        # Create lease
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1200.00"),
            status=LeaseStatus.DRAFT
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Send lease
        response = client.post(
            f"/api/leases/{lease.id}/send",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["sent_at"] is not None
    
    def test_send_lease_requires_draft_status(self, client: TestClient, auth_landlord_token, approved_application, db_session):
        """Test that only DRAFT lease can be sent"""
        from app.models.lease import Lease, LeaseStatus
        
        # Create SENT lease
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1200.00"),
            status=LeaseStatus.SENT
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Try to send again
        response = client.post(
            f"/api/leases/{lease.id}/send",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 400
        response_data = response.json()
        detail = response_data.get("detail", response_data)
        error_text = str(detail)
        if isinstance(detail, dict):
            error_text = detail.get("message", str(detail))
        assert "DRAFT" in error_text or "draft" in error_text.lower()


class TestLeaseSigning:
    """Test lease signing by tenant"""
    
    def test_sign_lease_success(self, client: TestClient, auth_tenant_token, approved_application, db_session):
        """Test successful lease signing by tenant"""
        from app.models.lease import Lease, LeaseStatus
        
        # Create and send lease
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1200.00"),
            status=LeaseStatus.SENT
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Sign lease
        response = client.post(
            f"/api/leases/{lease.id}/sign",
            json={"signature": "John Doe"},
            headers={"Authorization": f"Bearer {auth_tenant_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "signed"
        assert data["signed_at"] is not None
        assert len(data["signatures"]) == 1
        assert data["signatures"][0]["role"] == "tenant"
        
        # Verify application status stays APPROVED (only updates to ACTIVE_LEASE on activation)
        db_session.refresh(approved_application)
        assert approved_application.status == ApplicationStatus.APPROVED
    
    def test_sign_lease_idempotent(self, client: TestClient, auth_tenant_token, approved_application, db_session):
        """Test that tenant cannot sign lease twice"""
        from app.models.lease import Lease, LeaseStatus, LeaseSignature
        
        # Create and send lease
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1200.00"),
            status=LeaseStatus.SENT
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Sign first time
        response1 = client.post(
            f"/api/leases/{lease.id}/sign",
            json={"signature": "John Doe"},
            headers={"Authorization": f"Bearer {auth_tenant_token}"}
        )
        assert response1.status_code == 200
        
        # Try to sign again
        response2 = client.post(
            f"/api/leases/{lease.id}/sign",
            json={"signature": "John Doe"},
            headers={"Authorization": f"Bearer {auth_tenant_token}"}
        )
        
        assert response2.status_code == 400
        response2_data = response2.json()
        detail = response2_data.get("detail", response2_data)
        error_text = str(detail)
        if isinstance(detail, dict):
            error_text = detail.get("message", str(detail))
        assert "already signed" in error_text or "signed" in error_text.lower()


class TestLeaseCounterSign:
    """Test lease counter-signing by landlord"""
    
    def test_counter_sign_lease_success(self, client: TestClient, auth_landlord_token, auth_tenant_token, approved_application, db_session):
        """Test successful counter-signing by landlord"""
        from app.models.lease import Lease, LeaseStatus, LeaseSignature
        
        # Create lease, send, and tenant signs
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1200.00"),
            status=LeaseStatus.SENT
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Tenant signs
        tenant_signature = LeaseSignature(
            lease_id=lease.id,
            user_id=approved_application.applicant_id,
            role="tenant",
            signature_text="John Doe",
            signed_at=datetime.now(timezone.utc)
        )
        db_session.add(tenant_signature)
        lease.status = LeaseStatus.SIGNED
        db_session.commit()
        db_session.refresh(lease)
        
        # Landlord counter-signs
        response = client.post(
            f"/api/leases/{lease.id}/counter-sign",
            json={"signature": "Landlord Name"},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "counter_signed"
        assert len(data["signatures"]) == 2
        assert any(s["role"] == "landlord" for s in data["signatures"])


class TestLeaseActivation:
    """Test lease activation"""
    
    def test_activate_lease_success(self, client: TestClient, auth_landlord_token, approved_application, db_session):
        """Test successful lease activation"""
        from app.models.lease import Lease, LeaseStatus, LeaseSignature
        
        # Create lease, send, and tenant signs
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1200.00"),
            status=LeaseStatus.SENT
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Tenant signs
        tenant_signature = LeaseSignature(
            lease_id=lease.id,
            user_id=approved_application.applicant_id,
            role="tenant",
            signature_text="John Doe",
            signed_at=datetime.now(timezone.utc)
        )
        db_session.add(tenant_signature)
        lease.status = LeaseStatus.SIGNED
        db_session.commit()
        db_session.refresh(lease)
        
        # Activate lease
        response = client.post(
            f"/api/leases/{lease.id}/activate",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        assert data["activated_at"] is not None
        
        # Verify application status
        db_session.refresh(approved_application)
        assert approved_application.status == ApplicationStatus.ACTIVE_LEASE
        
        # Verify property is unavailable
        db_session.refresh(approved_application.property)
        assert approved_application.property.is_active == False


class TestCompleteLeaseFlow:
    """Test complete lease workflow end-to-end"""
    
    def test_complete_lease_workflow(self, client: TestClient, auth_landlord_token, auth_tenant_token, approved_application):
        """Test complete workflow: create → send → sign → counter-sign → activate"""
        
        # Step 1: Create lease
        lease_data = {
            "application_id": approved_application.id,
            "rent": "1200.00",
            "deposit": "1200.00",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=395)).isoformat(),
            "terms": "Standard lease terms"
        }
        
        create_response = client.post(
            "/api/leases",
            json=lease_data,
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert create_response.status_code == 201
        lease_id = create_response.json()["id"]
        
        # Step 2: Send lease
        send_response = client.post(
            f"/api/leases/{lease_id}/send",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert send_response.status_code == 200
        assert send_response.json()["status"] == "sent"
        
        # Step 3: Tenant signs
        sign_response = client.post(
            f"/api/leases/{lease_id}/sign",
            json={"signature": "John Doe"},
            headers={"Authorization": f"Bearer {auth_tenant_token}"}
        )
        assert sign_response.status_code == 200
        assert sign_response.json()["status"] == "signed"
        
        # Step 4: Landlord counter-signs
        counter_sign_response = client.post(
            f"/api/leases/{lease_id}/counter-sign",
            json={"signature": "Landlord Name"},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert counter_sign_response.status_code == 200
        assert counter_sign_response.json()["status"] == "counter_signed"
        
        # Step 5: Activate lease
        activate_response = client.post(
            f"/api/leases/{lease_id}/activate",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert activate_response.status_code == 200
        assert activate_response.json()["status"] == "active"
        
        print(f"[PASS] Complete lease workflow verified: DRAFT → SENT → SIGNED → COUNTER_SIGNED → ACTIVE")

