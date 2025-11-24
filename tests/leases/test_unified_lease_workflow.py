"""
Enterprise-grade tests for unified lease workflow
Tests dual-origin lease creation (application-driven and manual)
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi.testclient import TestClient

from app.models.lease import LeaseStatus, LeaseSignature
from app.models.application import ApplicationStatus
from app.models.property import PropertyType, PropertyStatus, ListingType
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
    from app.models.property import Property
    
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
        rent_price=1500.00,
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
    from app.models.application import Application
    
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


class TestManualLeaseCreation:
    """Test manual lease creation (property_id + tenant_id)"""
    
    def test_create_manual_lease_success(self, client: TestClient, auth_landlord_token, test_property_for_lease, test_user_tenant):
        """Test successful manual lease creation"""
        lease_data = {
            "property_id": test_property_for_lease.id,
            "tenant_id": test_user_tenant.id,
            "rent": "1500.00",
            "deposit": "1500.00",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=395)).isoformat(),
            "terms": "Manual lease terms"
        }
        
        response = client.post(
            "/api/leases",
            json=lease_data,
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["application_id"] is None
        assert data["property_id"] == test_property_for_lease.id
        assert data["tenant_id"] == test_user_tenant.id
        assert isinstance(data["rent"], (int, float))
    
    def test_create_manual_lease_missing_property_id(self, client: TestClient, auth_landlord_token, test_user_tenant):
        """Test manual lease creation fails without property_id"""
        lease_data = {
            "tenant_id": test_user_tenant.id,
            "rent": "1500.00",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=395)).isoformat()
        }
        
        response = client.post(
            "/api/leases",
            json=lease_data,
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 422
        response_data = response.json()
        detail = response_data.get("detail", [])
        if isinstance(detail, list):
            assert any("property_id" in str(err).lower() for err in detail)
        else:
            assert "property_id" in str(detail).lower() or "required" in str(detail).lower()
    
    def test_create_manual_lease_missing_tenant_id(self, client: TestClient, auth_landlord_token, test_property_for_lease):
        """Test manual lease creation fails without tenant_id"""
        lease_data = {
            "property_id": test_property_for_lease.id,
            "rent": "1500.00",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=395)).isoformat()
        }
        
        response = client.post(
            "/api/leases",
            json=lease_data,
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 422
        response_data = response.json()
        detail = response_data.get("detail", [])
        if isinstance(detail, list):
            assert any("tenant_id" in str(err).lower() for err in detail)
        else:
            assert "tenant_id" in str(detail).lower() or "required" in str(detail).lower()


class TestSchemaValidation:
    """Test schema validation for dual-origin lease creation"""
    
    def test_application_driven_with_property_id_fails(self, client: TestClient, auth_landlord_token, approved_application, test_property_for_lease):
        """Test that providing property_id with application_id fails validation"""
        lease_data = {
            "application_id": approved_application.id,
            "property_id": test_property_for_lease.id,  # Should not be provided
            "rent": "1500.00",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=395)).isoformat()
        }
        
        response = client.post(
            "/api/leases",
            json=lease_data,
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 422
        response_data = response.json()
        detail = response_data.get("detail", response_data)
        error_text = str(detail).lower()
        assert "property_id" in error_text or "cannot provide" in error_text or "application_id" in error_text
    
    def test_application_driven_with_tenant_id_fails(self, client: TestClient, auth_landlord_token, approved_application, test_user_tenant):
        """Test that providing tenant_id with application_id fails validation"""
        lease_data = {
            "application_id": approved_application.id,
            "tenant_id": test_user_tenant.id,  # Should not be provided
            "rent": "1500.00",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=395)).isoformat()
        }
        
        response = client.post(
            "/api/leases",
            json=lease_data,
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        
        assert response.status_code == 422
        response_data = response.json()
        detail = response_data.get("detail", response_data)
        error_text = str(detail).lower()
        assert "tenant_id" in error_text or "cannot provide" in error_text or "application_id" in error_text


class TestAutomaticLeaseCreation:
    """Test automatic lease creation on application approval"""
    
    def test_auto_create_lease_on_approval(self, client: TestClient, auth_landlord_token, db_session, test_user_landlord, test_user_tenant, test_property_for_lease):
        """Test that lease is automatically created when application is approved"""
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
        
        # Review application
        review_response = client.post(
            f"/api/landlord/applications/{app.id}/review",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert review_response.status_code == 200
        
        # Approve application (should auto-create lease)
        approve_response = client.post(
            f"/api/landlord/applications/{app.id}/approve",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert approve_response.status_code == 200
        
        # Check lease was auto-created
        lease_response = client.get(
            f"/api/leases/application/{app.id}",
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert lease_response.status_code == 200
        lease_data = lease_response.json()
        assert lease_data["status"] == "draft"
        assert lease_data["application_id"] == app.id
        assert lease_data["property_id"] == test_property_for_lease.id
        assert lease_data["tenant_id"] == test_user_tenant.id


class TestTerminateLease:
    """Test lease termination functionality"""
    
    def test_terminate_active_lease_success(self, client: TestClient, auth_landlord_token, auth_tenant_token, approved_application, db_session):
        """Test successful lease termination"""
        from app.models.lease import Lease, LeaseSignature
        
        # Create and fully sign lease
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1500.00"),
            status=LeaseStatus.COUNTER_SIGNED,
            start_date=datetime.now(timezone.utc) - timedelta(days=1)  # Start date in past
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Add signatures
        tenant_sig = LeaseSignature(
            lease_id=lease.id,
            user_id=approved_application.applicant_id,
            role="tenant",
            signature_text="Tenant",
            signed_at=datetime.now(timezone.utc)
        )
        landlord_sig = LeaseSignature(
            lease_id=lease.id,
            user_id=approved_application.property.owner_id,
            role="landlord",
            signature_text="Landlord",
            signed_at=datetime.now(timezone.utc)
        )
        db_session.add(tenant_sig)
        db_session.add(landlord_sig)
        db_session.commit()
        
        # Activate lease
        activate_response = client.post(
            f"/api/leases/{lease.id}/activate",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert activate_response.status_code == 200
        assert activate_response.json()["status"] == "active"
        
        # Terminate lease
        terminate_response = client.post(
            f"/api/leases/{lease.id}/terminate",
            json={"reason": "Mutual agreement"},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert terminate_response.status_code == 200
        data = terminate_response.json()
        assert data["status"] == "terminated"
        
        # Verify application status updated to CLOSED
        db_session.refresh(approved_application)
        assert approved_application.status == ApplicationStatus.CLOSED
        
        # Verify property is available again
        db_session.refresh(approved_application.property)
        assert approved_application.property.is_active == True
    
    def test_terminate_lease_only_active(self, client: TestClient, auth_landlord_token, approved_application, db_session):
        """Test that only ACTIVE leases can be terminated"""
        from app.models.lease import Lease
        
        # Create DRAFT lease
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1500.00"),
            status=LeaseStatus.DRAFT
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Try to terminate DRAFT lease
        terminate_response = client.post(
            f"/api/leases/{lease.id}/terminate",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert terminate_response.status_code == 400
        response_data = terminate_response.json()
        detail = response_data.get("detail", response_data)
        error_text = str(detail).lower()
        if isinstance(detail, dict):
            error_text = detail.get("message", str(detail)).lower()
        assert "active" in error_text


class TestStatusTransitionEnforcement:
    """Test strict status transition enforcement"""
    
    def test_sign_only_from_sent(self, client: TestClient, auth_tenant_token, approved_application, db_session):
        """Test that tenant can only sign from SENT status (not DRAFT)"""
        from app.models.lease import Lease
        
        # Create DRAFT lease
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1500.00"),
            status=LeaseStatus.DRAFT
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Try to sign DRAFT lease (should fail)
        sign_response = client.post(
            f"/api/leases/{lease.id}/sign",
            json={"signature": "Tenant"},
            headers={"Authorization": f"Bearer {auth_tenant_token}"}
        )
        assert sign_response.status_code == 400
        error_text = str(sign_response.json()["detail"]).lower()
        assert "sent" in error_text
    
    def test_activate_only_from_counter_signed(self, client: TestClient, auth_landlord_token, approved_application, db_session):
        """Test that lease can only be activated from COUNTER_SIGNED (not SIGNED)"""
        from app.models.lease import Lease, LeaseSignature
        
        # Create and send lease
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1500.00"),
            status=LeaseStatus.SENT
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Tenant signs
        tenant_sig = LeaseSignature(
            lease_id=lease.id,
            user_id=approved_application.applicant_id,
            role="tenant",
            signature_text="Tenant",
            signed_at=datetime.now(timezone.utc)
        )
        db_session.add(tenant_sig)
        lease.status = LeaseStatus.SIGNED
        db_session.commit()
        db_session.refresh(lease)
        
        # Try to activate SIGNED lease (should fail - needs COUNTER_SIGNED)
        activate_response = client.post(
            f"/api/leases/{lease.id}/activate",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert activate_response.status_code == 400
        response_data = activate_response.json()
        detail = response_data.get("detail", response_data)
        error_text = str(detail).lower()
        if isinstance(detail, dict):
            error_text = detail.get("message", str(detail)).lower()
        assert "counter_signed" in error_text or "counter-signed" in error_text
    
    def test_activate_requires_start_date(self, client: TestClient, auth_landlord_token, approved_application, db_session):
        """Test that lease cannot be activated before start_date"""
        from app.models.lease import Lease, LeaseSignature
        
        # Create fully signed lease with future start date
        future_start = datetime.now(timezone.utc) + timedelta(days=30)
        lease = Lease(
            application_id=approved_application.id,
            landlord_id=approved_application.property.owner_id,
            tenant_id=approved_application.applicant_id,
            property_id=approved_application.property_id,
            rent=Decimal("1500.00"),
            status=LeaseStatus.COUNTER_SIGNED,
            start_date=future_start
        )
        db_session.add(lease)
        db_session.commit()
        db_session.refresh(lease)
        
        # Add both signatures
        tenant_sig = LeaseSignature(
            lease_id=lease.id,
            user_id=approved_application.applicant_id,
            role="tenant",
            signature_text="Tenant",
            signed_at=datetime.now(timezone.utc)
        )
        landlord_sig = LeaseSignature(
            lease_id=lease.id,
            user_id=approved_application.property.owner_id,
            role="landlord",
            signature_text="Landlord",
            signed_at=datetime.now(timezone.utc)
        )
        db_session.add(tenant_sig)
        db_session.add(landlord_sig)
        db_session.commit()
        
        # Try to activate before start date (should fail)
        activate_response = client.post(
            f"/api/leases/{lease.id}/activate",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert activate_response.status_code == 400
        error_text = str(activate_response.json()["detail"]).lower()
        assert "start date" in error_text or "start_date" in error_text


class TestUnifiedWorkflow:
    """Test that both application-driven and manual leases follow same workflow"""
    
    def test_manual_lease_workflow(self, client: TestClient, auth_landlord_token, auth_tenant_token, test_property_for_lease, test_user_tenant):
        """Test complete workflow for manual lease"""
        # Create manual lease
        lease_data = {
            "property_id": test_property_for_lease.id,
            "tenant_id": test_user_tenant.id,
            "rent": "1500.00",
            "deposit": "1500.00",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=395)).isoformat()
        }
        
        create_response = client.post(
            "/api/leases",
            json=lease_data,
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert create_response.status_code == 201
        lease_id = create_response.json()["id"]
        assert create_response.json()["application_id"] is None
        
        # Send lease
        send_response = client.post(
            f"/api/leases/{lease_id}/send",
            json={},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert send_response.status_code == 200
        assert send_response.json()["status"] == "sent"
        
        # Tenant signs
        sign_response = client.post(
            f"/api/leases/{lease_id}/sign",
            json={"signature": "Tenant"},
            headers={"Authorization": f"Bearer {auth_tenant_token}"}
        )
        assert sign_response.status_code == 200
        assert sign_response.json()["status"] == "signed"
        
        # Landlord counter-signs
        counter_sign_response = client.post(
            f"/api/leases/{lease_id}/counter-sign",
            json={"signature": "Landlord"},
            headers={"Authorization": f"Bearer {auth_landlord_token}"}
        )
        assert counter_sign_response.status_code == 200
        assert counter_sign_response.json()["status"] == "counter_signed"
        
        print("[PASS] Manual lease workflow verified: DRAFT → SENT → SIGNED → COUNTER_SIGNED")

