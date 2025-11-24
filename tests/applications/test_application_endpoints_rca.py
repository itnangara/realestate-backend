"""
Comprehensive Application Endpoint Tests using RCA Framework

Following RCA Framework principles:
1. Observe & Document - Test each endpoint and document expected behavior
2. Instrument - Add logging to verify behavior at each layer
3. Analyze - Verify status transitions, business rules, authorization
4. Verify - Confirm all tests pass with evidence

Tests cover:
- Tenant endpoints (create, list, get, update, attach documents)
- Landlord endpoints (list, get, approve, reject, request-info, sign, activate)
- Admin endpoints (list, get)
- Status transitions (draft → submitted → reviewed → approved → signed → active_lease)
- Business rules (duplicate check, active lease check, property availability)
- Authorization (tenant sees only own, landlord sees only own properties)
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.models.application import Application, ApplicationStatus
from app.models.property import Property, PropertyStatus, ListingType, PropertyType
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.document import Document, DocumentType, DocumentStatus
from app.services.auth_service import AuthService


# ============================================================================
# Test Fixtures
# ============================================================================

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
    
    # Assign tenant role
    tenant_role = db_session.query(Role).filter(Role.name == "tenant").first()
    user_role = UserRole(user_id=user.id, role_id=tenant_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


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
    
    # Assign landlord role
    landlord_role = db_session.query(Role).filter(Role.name == "landlord").first()
    user_role = UserRole(user_id=user.id, role_id=landlord_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


@pytest.fixture(scope="function")
def tenant_token(client, test_user_tenant):
    """Get tenant authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "tenant@test.com",
        "password": "tenantpassword"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="function")
def landlord_token(client, test_user_landlord):
    """Get landlord authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "landlord@test.com",
        "password": "landlordpassword"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="function")
def tenant_headers(tenant_token):
    """Tenant authentication headers"""
    return {"Authorization": f"Bearer {tenant_token}"}


@pytest.fixture(scope="function")
def landlord_headers(landlord_token):
    """Landlord authentication headers"""
    return {"Authorization": f"Bearer {landlord_token}"}


@pytest.fixture(scope="function")
def test_property_for_rent(db_session, test_user_landlord):
    """Create a test property for rent"""
    property = Property(
        title="Test Rental Property",
        description="Property for testing applications",
        property_type=PropertyType.APARTMENT,
        listing_type=ListingType.FOR_RENT,
        status=PropertyStatus.ACTIVE,
        address="123 Test Street",
        city="Test City",
        state="TS",
        zip_code="12345",
        country="USA",
        rent_price=1500.0,
        bedrooms=2,
        bathrooms=1.5,
        square_feet=1000,
        owner_id=test_user_landlord.id,
        is_active=True
    )
    db_session.add(property)
    db_session.commit()
    db_session.refresh(property)
    return property


# ============================================================================
# RCA Step 1: Observe & Document - Tenant Endpoints
# ============================================================================

class TestTenantEndpoints:
    """Test tenant application endpoints"""
    
    def test_create_application_starts_in_draft(self, client, tenant_headers, test_property_for_rent):
        """
        RCA: Observe - Application creation should start in DRAFT status
        Expected: POST /api/tenant/applications creates application with status='draft'
        """
        application_data = {
            "property_id": test_property_for_rent.id,
            "message": "I'm interested in renting this property",
            "move_in_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "lease_duration": 12,
            "annual_income": 50000,
            "credit_score": 700,
            "background_check_consent": True
        }
        
        response = client.post("/api/tenant/applications", json=application_data, headers=tenant_headers)
        
        # Document: Verify response
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["property_id"] == test_property_for_rent.id
        assert data["applicant_id"] is not None
        
        print(f"✅ Application created with status: {data['status']}")
    
    def test_create_application_requires_tenant_role(self, client, buyer_headers, test_property_for_rent):
        """
        RCA: Observe - Non-tenant users cannot create applications
        Expected: 403 Forbidden
        """
        application_data = {
            "property_id": test_property_for_rent.id,
            "message": "Test application"
        }
        
        response = client.post("/api/tenant/applications", json=application_data, headers=buyer_headers)
        
        assert response.status_code == 403
        assert "tenant" in response.json()["message"].lower()
    
    def test_get_tenant_applications_only_own(self, client, tenant_headers, test_property_for_rent, db_session, test_user_tenant):
        """
        RCA: Observe - Tenant can only see their own applications
        Expected: GET /api/tenant/applications returns only applications where applicant_id = current_user.id
        """
        # Create application for tenant
        app1 = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.DRAFT,
            message="My application"
        )
        db_session.add(app1)
        
        # Create application for another user (should not appear)
        other_user = User(
            email="other@test.com",
            username="other_user",
            first_name="Other",
            last_name="User",
            hashed_password="hash",
            is_verified=True
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)
        
        app2 = Application(
            property_id=test_property_for_rent.id,
            applicant_id=other_user.id,
            status=ApplicationStatus.DRAFT,
            message="Other user's application"
        )
        db_session.add(app2)
        db_session.commit()
        
        response = client.get("/api/tenant/applications", headers=tenant_headers)
        
        assert response.status_code == 200
        applications = response.json()
        assert len(applications) == 1
        assert applications[0]["id"] == app1.id
        assert applications[0]["applicant_id"] == test_user_tenant.id
        
        print(f"✅ Tenant sees only {len(applications)} application(s) (their own)")
    
    def test_update_application_draft_to_submitted(self, client, tenant_headers, test_property_for_rent, db_session, test_user_tenant):
        """
        RCA: Observe - Status transition DRAFT → SUBMITTED → REVIEWED
        Expected: Updating status to SUBMITTED automatically moves to REVIEWED
        """
        # Create draft application
        app = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.DRAFT,
            message="Draft application"
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        
        # Update to submitted
        update_data = {
            "status": "submitted"
        }
        
        response = client.patch(f"/api/tenant/applications/{app.id}", json=update_data, headers=tenant_headers)
        
        assert response.status_code == 200
        data = response.json()
        # System should automatically move SUBMITTED → REVIEWED
        assert data["status"] == "reviewed"
        
        print(f"✅ Status transition: DRAFT → SUBMITTED → REVIEWED (final: {data['status']})")
    
    def test_cannot_edit_application_after_submitted(self, client, tenant_headers, test_property_for_rent, db_session, test_user_tenant):
        """
        RCA: Observe - Cannot edit application after SUBMITTED unless NEEDS_INFO
        Expected: 400 Bad Request when trying to edit SUBMITTED application
        """
        # Create submitted application
        app = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.REVIEWED,  # Already reviewed
            message="Submitted application"
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        
        # Try to update
        update_data = {
            "message": "Updated message"
        }
        
        response = client.patch(f"/api/tenant/applications/{app.id}", json=update_data, headers=tenant_headers)
        
        assert response.status_code == 400
        assert "cannot edit" in response.json()["message"].lower()
        
        print(f"✅ Correctly prevented editing application in {app.status.value} status")
    
    def test_duplicate_application_prevention(self, client, tenant_headers, test_property_for_rent, db_session, test_user_tenant):
        """
        RCA: Observe - Cannot apply twice to same property
        Expected: 400 Bad Request when creating duplicate application
        """
        # Create first application
        app1 = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.DRAFT,
            message="First application"
        )
        db_session.add(app1)
        db_session.commit()
        
        # Try to create second application for same property
        application_data = {
            "property_id": test_property_for_rent.id,
            "message": "Duplicate application"
        }
        
        response = client.post("/api/tenant/applications", json=application_data, headers=tenant_headers)
        
        assert response.status_code == 400
        assert "duplicate" in response.json()["message"].lower() or "already have" in response.json()["message"].lower()
        
        print(f"✅ Duplicate application correctly prevented")


# ============================================================================
# RCA Step 2: Instrument & Analyze - Landlord Endpoints
# ============================================================================

class TestLandlordEndpoints:
    """Test landlord application endpoints"""
    
    def test_landlord_can_see_only_own_properties_applications(self, client, landlord_headers, db_session, test_user_landlord, test_user_tenant):
        """
        RCA: Instrument & Analyze - Landlord sees only applications for their properties
        Expected: GET /api/landlord/applications returns only apps for properties where owner_id = landlord.id
        """
        # Create property owned by landlord
        property1 = Property(
            title="Landlord's Property",
            property_type=PropertyType.APARTMENT,
            listing_type=ListingType.FOR_RENT,
            status=PropertyStatus.ACTIVE,
            address="123 Landlord St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            owner_id=test_user_landlord.id,
            is_active=True
        )
        db_session.add(property1)
        
        # Create property owned by someone else
        other_landlord = User(
            email="other_landlord@test.com",
            username="other_landlord",
            first_name="Other",
            last_name="Landlord",
            hashed_password="hash",
            is_verified=True
        )
        db_session.add(other_landlord)
        db_session.commit()
        db_session.refresh(other_landlord)
        
        property2 = Property(
            title="Other Landlord's Property",
            property_type=PropertyType.APARTMENT,
            listing_type=ListingType.FOR_RENT,
            status=PropertyStatus.ACTIVE,
            address="456 Other St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            owner_id=other_landlord.id,
            is_active=True
        )
        db_session.add(property2)
        db_session.commit()
        db_session.refresh(property1)
        db_session.refresh(property2)
        
        # Create applications
        app1 = Application(
            property_id=property1.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.REVIEWED,
            message="Application for landlord's property"
        )
        db_session.add(app1)
        
        app2 = Application(
            property_id=property2.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.REVIEWED,
            message="Application for other landlord's property"
        )
        db_session.add(app2)
        db_session.commit()
        
        # Landlord should only see app1
        response = client.get("/api/landlord/applications", headers=landlord_headers)
        
        assert response.status_code == 200
        applications = response.json()
        assert len(applications) == 1
        assert applications[0]["id"] == app1.id
        assert applications[0]["property_id"] == property1.id
        
        print(f"✅ Landlord sees only {len(applications)} application(s) (for their properties)")
    
    def test_landlord_approve_application(self, client, landlord_headers, db_session, test_user_landlord, test_user_tenant, test_property_for_rent):
        """
        RCA: Instrument & Analyze - Status transition REVIEWED → APPROVED
        Expected: POST /api/landlord/applications/{id}/approve moves status to APPROVED
        """
        # Create reviewed application
        app = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.REVIEWED,
            message="Application to approve"
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        
        # Approve
        response = client.post(f"/api/landlord/applications/{app.id}/approve", headers=landlord_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        
        print(f"✅ Status transition: REVIEWED → APPROVED (final: {data['status']})")
    
    def test_landlord_cannot_approve_non_reviewed(self, client, landlord_headers, db_session, test_user_landlord, test_user_tenant, test_property_for_rent):
        """
        RCA: Analyze - Cannot approve application not in REVIEWED status
        Expected: 400 Bad Request
        """
        # Create draft application
        app = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.DRAFT,
            message="Draft application"
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        
        # Try to approve
        response = client.post(f"/api/landlord/applications/{app.id}/approve", headers=landlord_headers)
        
        assert response.status_code == 400
        assert "reviewed" in response.json()["message"].lower()
        
        print(f"✅ Correctly prevented approving application in {app.status.value} status")
    
    def test_landlord_reject_application(self, client, landlord_headers, db_session, test_user_landlord, test_user_tenant, test_property_for_rent):
        """
        RCA: Instrument & Analyze - Status transition REVIEWED → REJECTED
        Expected: POST /api/landlord/applications/{id}/reject moves status to REJECTED
        """
        app = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.REVIEWED,
            message="Application to reject"
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        
        response = client.post(f"/api/landlord/applications/{app.id}/reject", headers=landlord_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        
        print(f"✅ Status transition: REVIEWED → REJECTED (final: {data['status']})")
    
    def test_landlord_request_more_info(self, client, landlord_headers, db_session, test_user_landlord, test_user_tenant, test_property_for_rent):
        """
        RCA: Instrument & Analyze - Status transition REVIEWED → NEEDS_INFO
        Expected: POST /api/landlord/applications/{id}/request-info moves status to NEEDS_INFO
        """
        app = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.REVIEWED,
            message="Application needing more info"
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        
        response = client.post(f"/api/landlord/applications/{app.id}/request-info", headers=landlord_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "needs_info"
        
        print(f"✅ Status transition: REVIEWED → NEEDS_INFO (final: {data['status']})")
    
    def test_tenant_can_resubmit_after_needs_info(self, client, tenant_headers, db_session, test_user_tenant, test_property_for_rent):
        """
        RCA: Analyze - Status transition NEEDS_INFO → SUBMITTED → REVIEWED
        Expected: Tenant can resubmit after NEEDS_INFO
        """
        app = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.NEEDS_INFO,
            message="Application needing more info"
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        
        # Resubmit
        update_data = {
            "status": "submitted",
            "message": "Updated application with requested info"
        }
        
        response = client.patch(f"/api/tenant/applications/{app.id}", json=update_data, headers=tenant_headers)
        
        assert response.status_code == 200
        data = response.json()
        # Should automatically move to REVIEWED
        assert data["status"] == "reviewed"
        
        print(f"✅ Status transition: NEEDS_INFO → SUBMITTED → REVIEWED (final: {data['status']})")


# ============================================================================
# RCA Step 3: Analyze - Business Rules
# ============================================================================

class TestBusinessRules:
    """Test enterprise-grade business rules"""
    
    def test_cannot_apply_with_active_lease(self, client, tenant_headers, db_session, test_user_tenant, test_property_for_rent):
        """
        RCA: Analyze - Cannot apply if tenant has active lease
        Expected: 400 Bad Request
        """
        # Create active lease
        active_lease = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.ACTIVE_LEASE,
            message="Active lease"
        )
        db_session.add(active_lease)
        db_session.commit()
        
        # Try to create new application
        application_data = {
            "property_id": test_property_for_rent.id,
            "message": "New application"
        }
        
        response = client.post("/api/tenant/applications", json=application_data, headers=tenant_headers)
        
        assert response.status_code == 400
        assert "active lease" in response.json()["message"].lower()
        
        print(f"✅ Correctly prevented application when tenant has active lease")
    
    def test_sign_lease_auto_withdraws_other_applications(self, client, landlord_headers, db_session, test_user_landlord, test_user_tenant, test_property_for_rent):
        """
        RCA: Analyze - Signing lease auto-withdraws other applications
        Expected: Other pending/approved applications become WITHDRAWN
        """
        # Create approved application to sign
        app1 = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.APPROVED,
            message="Application to sign"
        )
        db_session.add(app1)
        
        # Create other pending application (should be withdrawn)
        app2 = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.REVIEWED,
            message="Other application"
        )
        db_session.add(app2)
        db_session.commit()
        db_session.refresh(app1)
        db_session.refresh(app2)
        
        # Sign lease
        response = client.post(f"/api/landlord/applications/{app1.id}/sign", headers=landlord_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "signed"
        
        # Check other application was withdrawn
        db_session.refresh(app2)
        assert app2.status == ApplicationStatus.WITHDRAWN
        
        print(f"✅ Signing lease auto-withdrew {1} other application(s)")
    
    def test_activate_lease_auto_withdraws_other_applications(self, client, landlord_headers, db_session, test_user_landlord, test_user_tenant, test_property_for_rent):
        """
        RCA: Analyze - Activating lease auto-withdraws other applications
        Expected: Other applications become WITHDRAWN
        """
        # Create signed application to activate
        app1 = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.SIGNED,
            message="Application to activate",
            lease_signed_at=datetime.now(timezone.utc)
        )
        db_session.add(app1)
        
        # Create other application (should be withdrawn)
        app2 = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.APPROVED,
            message="Other application"
        )
        db_session.add(app2)
        db_session.commit()
        db_session.refresh(app1)
        db_session.refresh(app2)
        
        # Activate lease
        response = client.post(f"/api/landlord/applications/{app1.id}/activate", headers=landlord_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active_lease"
        
        # Check other application was withdrawn
        db_session.refresh(app2)
        assert app2.status == ApplicationStatus.WITHDRAWN
        
        print(f"✅ Activating lease auto-withdrew {1} other application(s)")


# ============================================================================
# RCA Step 4: Verify - Admin Endpoints
# ============================================================================

class TestDocumentAttachment:
    """Test document attachment to applications"""
    
    def test_attach_documents_to_application(self, client, tenant_headers, db_session, test_user_tenant, test_property_for_rent):
        """
        RCA: Verify - Tenant can attach documents to their application
        Expected: POST /api/tenant/applications/{id}/documents attaches documents
        """
        # Create draft application
        app = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.DRAFT,
            message="Application with documents"
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        
        # Create test documents (using UUID for file_id)
        from uuid import uuid4
        doc1_uuid = uuid4()
        doc2_uuid = uuid4()
        
        doc1 = Document(
            file_id=doc1_uuid,
            user_id=test_user_tenant.id,
            file_name="test1.pdf",
            size=1000,
            mime_type="application/pdf",
            type=DocumentType.ID_FRONT,
            s3_key="test/key1",
            status=DocumentStatus.VERIFIED
        )
        doc2 = Document(
            file_id=doc2_uuid,
            user_id=test_user_tenant.id,
            file_name="test2.pdf",
            size=2000,
            mime_type="application/pdf",
            type=DocumentType.PROOF_OF_INCOME,
            s3_key="test/key2",
            status=DocumentStatus.VERIFIED
        )
        db_session.add(doc1)
        db_session.add(doc2)
        db_session.commit()
        
        # Attach documents (endpoint expects List[str] as body)
        from uuid import UUID
        document_ids = [str(doc1.file_id), str(doc2.file_id)]
        response = client.post(
            f"/api/tenant/applications/{app.id}/documents",
            json=document_ids,
            headers=tenant_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["documents_urls"]) == 2
        assert str(doc1.file_id) in data["documents_urls"]
        assert str(doc2.file_id) in data["documents_urls"]
        
        print(f"✅ Attached {len(data['documents_urls'])} document(s) to application")
    
    def test_cannot_attach_documents_to_submitted_application(self, client, tenant_headers, db_session, test_user_tenant, test_property_for_rent):
        """
        RCA: Verify - Cannot attach documents to submitted application
        Expected: 400 Bad Request
        """
        # Create submitted application
        app = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.REVIEWED,  # Already reviewed
            message="Submitted application"
        )
        db_session.add(app)
        db_session.commit()
        db_session.refresh(app)
        
        # Try to attach documents (using invalid UUID to test validation)
        from uuid import uuid4
        document_ids = [str(uuid4())]  # Non-existent document
        response = client.post(
            f"/api/tenant/applications/{app.id}/documents",
            json=document_ids,
            headers=tenant_headers
        )
        
        assert response.status_code == 400
        assert "cannot attach" in response.json()["message"].lower()
        
        print(f"✅ Correctly prevented attaching documents to {app.status.value} application")


class TestAdminEndpoints:
    """Test admin application endpoints"""
    
    def test_admin_can_see_all_applications(self, client, admin_headers, db_session, test_user_admin, test_user_tenant, test_property_for_rent):
        """
        RCA: Verify - Admin can see all applications
        Expected: GET /api/admin/applications returns all applications
        """
        # Create multiple applications
        app1 = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.DRAFT,
            message="Application 1"
        )
        app2 = Application(
            property_id=test_property_for_rent.id,
            applicant_id=test_user_tenant.id,
            status=ApplicationStatus.REVIEWED,
            message="Application 2"
        )
        db_session.add(app1)
        db_session.add(app2)
        db_session.commit()
        
        response = client.get("/api/admin/applications", headers=admin_headers)
        
        assert response.status_code == 200
        applications = response.json()
        assert len(applications) >= 2
        
        print(f"✅ Admin sees {len(applications)} application(s) (all applications)")


# ============================================================================
# RCA Step 5: Verify - Complete Status Transition Flow
# ============================================================================

class TestCompleteStatusFlow:
    """Test complete application lifecycle"""
    
    def test_complete_application_lifecycle(self, client, tenant_headers, landlord_headers, db_session, test_user_tenant, test_user_landlord, test_property_for_rent):
        """
        RCA: Verify - Complete status transition flow
        Expected: DRAFT → SUBMITTED → REVIEWED → APPROVED → SIGNED → ACTIVE_LEASE
        """
        # Step 1: Create application (DRAFT)
        application_data = {
            "property_id": test_property_for_rent.id,
            "message": "Complete lifecycle test",
            "move_in_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "lease_duration": 12
        }
        response = client.post("/api/tenant/applications", json=application_data, headers=tenant_headers)
        assert response.status_code == 201
        app_id = response.json()["id"]
        assert response.json()["status"] == "draft"
        print("✅ Step 1: Created application in DRAFT status")
        
        # Step 2: Submit application (DRAFT → SUBMITTED → REVIEWED)
        update_data = {"status": "submitted"}
        response = client.patch(f"/api/tenant/applications/{app_id}", json=update_data, headers=tenant_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "reviewed"
        print("✅ Step 2: Submitted application (DRAFT → SUBMITTED → REVIEWED)")
        
        # Step 3: Approve application (REVIEWED → APPROVED)
        response = client.post(f"/api/landlord/applications/{app_id}/approve", headers=landlord_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        print("✅ Step 3: Approved application (REVIEWED → APPROVED)")
        
        # Step 4: Sign lease (APPROVED → SIGNED)
        response = client.post(f"/api/landlord/applications/{app_id}/sign", headers=landlord_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "signed"
        assert response.json()["lease_signed_at"] is not None
        print("✅ Step 4: Signed lease (APPROVED → SIGNED)")
        
        # Step 5: Activate lease (SIGNED → ACTIVE_LEASE)
        response = client.post(f"/api/landlord/applications/{app_id}/activate", headers=landlord_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "active_lease"
        print("✅ Step 5: Activated lease (SIGNED → ACTIVE_LEASE)")
        
        print("\n🎉 Complete lifecycle verified: DRAFT → SUBMITTED → REVIEWED → APPROVED → SIGNED → ACTIVE_LEASE")

