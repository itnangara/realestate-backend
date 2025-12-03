"""
Test: Multiple Properties Application Submission

This test verifies that a DRAFT application on Property 1 does NOT block
creating and submitting an application for Property 2.

Scenario:
- Property 1: Has existing DRAFT application
- Property 2: Should be able to create DRAFT and submit to SUBMITTED

Expected: Both applications should exist with correct statuses.
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.models.application import Application, ApplicationStatus
from app.models.property import Property, PropertyStatus, ListingType, PropertyType
from app.models.user_property import UserProperty, RelationshipType
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.services.auth_service import AuthService


@pytest.fixture(scope="function")
def test_tenant_user(db_session, auth_service, test_roles):
    """Create test tenant user"""
    hashed_password = auth_service.get_password_hash("tenantpass")
    user = User(
        email="testtenant@test.com",
        username="test_tenant",
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
def test_landlord_user(db_session, auth_service, test_roles):
    """Create test landlord user"""
    hashed_password = auth_service.get_password_hash("landlordpass")
    user = User(
        email="testlandlord@test.com",
        username="test_landlord",
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
def tenant_auth_token(client, test_tenant_user):
    """Get tenant authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "testtenant@test.com",
        "password": "tenantpass"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="function")
def tenant_headers(tenant_auth_token):
    """Tenant authentication headers"""
    return {"Authorization": f"Bearer {tenant_auth_token}"}


@pytest.fixture(scope="function")
def property_1(db_session, test_landlord_user):
    """Create Property 1"""
    property = Property(
        title="Property 1 - Test Rental",
        description="First test property",
        property_type=PropertyType.APARTMENT,
        listing_type=ListingType.FOR_RENT,
        status=PropertyStatus.ACTIVE,
        address="100 Property 1 Street",
        city="Test City",
        state="TS",
        zip_code="12345",
        country="USA",
        rent_price=1200.0,
        bedrooms=1,
        bathrooms=1.0,
        square_feet=800,
        is_active=True
    )
    db_session.add(property)
    db_session.flush()
    link = UserProperty(user_id=test_landlord_user.id, property_id=property.id, relationship_type=RelationshipType.LANDLORD)
    db_session.add(link)
    db_session.commit()
    db_session.refresh(property)
    return property


@pytest.fixture(scope="function")
def property_2(db_session, test_landlord_user):
    """Create Property 2"""
    property = Property(
        title="Property 2 - Test Rental",
        description="Second test property",
        property_type=PropertyType.APARTMENT,
        listing_type=ListingType.FOR_RENT,
        status=PropertyStatus.ACTIVE,
        address="200 Property 2 Street",
        city="Test City",
        state="TS",
        zip_code="12345",
        country="USA",
        rent_price=1500.0,
        bedrooms=2,
        bathrooms=1.5,
        square_feet=1000,
        is_active=True
    )
    db_session.add(property)
    db_session.flush()
    link = UserProperty(user_id=test_landlord_user.id, property_id=property.id, relationship_type=RelationshipType.LANDLORD)
    db_session.add(link)
    db_session.commit()
    db_session.refresh(property)
    return property


@pytest.fixture(scope="function")
def property_1_draft_application(db_session, test_tenant_user, property_1):
    """Create DRAFT application for Property 1"""
    application = Application(
        property_id=property_1.id,
        applicant_id=test_tenant_user.id,
        status=ApplicationStatus.DRAFT,
        message="Draft application for Property 1",
        annual_income=50000,
        credit_score=700,
        background_check_consent=True
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


class TestMultiplePropertiesSubmission:
    """
    Test that Property 1 DRAFT does NOT block Property 2 submission.
    
    This test provides evidence that the backend validation logic correctly
    allows multiple applications to different properties.
    """
    
    def test_property_2_can_be_created_and_submitted_when_property_1_has_draft(
        self,
        client,
        tenant_headers,
        property_1,
        property_2,
        property_1_draft_application,
        db_session,
        test_tenant_user
    ):
        """
        Test: Property 2 application creation and submission should succeed
        even when Property 1 has a DRAFT application.
        
        Steps:
        1. Verify Property 1 has DRAFT application (precondition)
        2. Create DRAFT application for Property 2 via API
        3. Update Property 2 application to SUBMITTED via API
        4. Verify both applications exist with correct statuses
        """
        
        # Step 1: Verify precondition - Property 1 has DRAFT application
        prop1_app = db_session.query(Application).filter(
            Application.id == property_1_draft_application.id
        ).first()
        
        assert prop1_app is not None, "Property 1 application should exist"
        assert prop1_app.status == ApplicationStatus.DRAFT, f"Property 1 should be DRAFT, got {prop1_app.status}"
        assert prop1_app.property_id == property_1.id, "Property 1 application should be for Property 1"
        print(f"[PASS] Precondition verified: Property 1 has DRAFT application (ID: {prop1_app.id})")
        
        # Step 2: Create DRAFT application for Property 2 via API
        application_data = {
            "property_id": property_2.id,
            "message": "I want to apply for Property 2",
            "move_in_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "lease_duration": 12,
            "annual_income": 60000,
            "credit_score": 750,
            "background_check_consent": True
        }
        
        create_response = client.post(
            "/api/tenant/applications",
            json=application_data,
            headers=tenant_headers
        )
        
        # Verify creation succeeded
        assert create_response.status_code == 201, (
            f"Property 2 application creation should succeed. "
            f"Got {create_response.status_code}: {create_response.text}"
        )
        
        create_data = create_response.json()
        property_2_app_id = create_data["id"]
        assert create_data["status"] == "draft", f"Property 2 should start as DRAFT, got {create_data['status']}"
        assert create_data["property_id"] == property_2.id, "Property 2 application should be for Property 2"
        print(f"[PASS] Step 2: Property 2 DRAFT application created (ID: {property_2_app_id})")
        
        # Step 3: Update Property 2 application to SUBMITTED via API
        update_data = {
            "status": "submitted"
        }
        
        update_response = client.patch(
            f"/api/tenant/applications/{property_2_app_id}",
            json=update_data,
            headers=tenant_headers
        )
        
        # Verify update succeeded
        assert update_response.status_code == 200, (
            f"Property 2 application submission should succeed. "
            f"Got {update_response.status_code}: {update_response.text}"
        )
        
        update_data_response = update_response.json()
        # Note: Backend automatically moves SUBMITTED → REVIEWED
        assert update_data_response["status"] in ["submitted", "reviewed"], (
            f"Property 2 should be SUBMITTED or REVIEWED after update, got {update_data_response['status']}"
        )
        print(f"[PASS] Step 3: Property 2 application submitted (Status: {update_data_response['status']})")
        
        # Step 4: Verify both applications exist with correct statuses
        # Refresh Property 1 application from database
        prop1_app_refreshed = db_session.query(Application).filter(
            Application.id == property_1_draft_application.id
        ).first()
        
        # Refresh Property 2 application from database
        prop2_app_refreshed = db_session.query(Application).filter(
            Application.id == property_2_app_id
        ).first()
        
        # Verify Property 1 still exists and is DRAFT
        assert prop1_app_refreshed is not None, "Property 1 application should still exist"
        assert prop1_app_refreshed.status == ApplicationStatus.DRAFT, (
            f"Property 1 should still be DRAFT, got {prop1_app_refreshed.status}"
        )
        assert prop1_app_refreshed.property_id == property_1.id, "Property 1 application should be for Property 1"
        
        # Verify Property 2 exists and is SUBMITTED/REVIEWED
        assert prop2_app_refreshed is not None, "Property 2 application should exist"
        assert prop2_app_refreshed.status in [ApplicationStatus.SUBMITTED, ApplicationStatus.REVIEWED], (
            f"Property 2 should be SUBMITTED or REVIEWED, got {prop2_app_refreshed.status}"
        )
        assert prop2_app_refreshed.property_id == property_2.id, "Property 2 application should be for Property 2"
        
        print(f"[PASS] Step 4: Both applications exist with correct statuses")
        print(f"   - Property 1 (ID: {prop1_app_refreshed.id}): {prop1_app_refreshed.status.value}")
        print(f"   - Property 2 (ID: {prop2_app_refreshed.id}): {prop2_app_refreshed.status.value}")
        
        # Final verification: Both applications belong to the same tenant
        assert prop1_app_refreshed.applicant_id == test_tenant_user.id, "Property 1 should belong to test tenant"
        assert prop2_app_refreshed.applicant_id == test_tenant_user.id, "Property 2 should belong to test tenant"
        assert prop1_app_refreshed.applicant_id == prop2_app_refreshed.applicant_id, (
            "Both applications should belong to the same tenant"
        )
        
        print(f"\n[SUCCESS] TEST PASSED: Property 1 DRAFT does NOT block Property 2 submission")
        print(f"   Evidence: Both applications exist independently with correct statuses")
        
        # Return evidence for manual inspection
        return {
            "property_1_application": {
                "id": prop1_app_refreshed.id,
                "property_id": prop1_app_refreshed.property_id,
                "status": prop1_app_refreshed.status.value,
                "applicant_id": prop1_app_refreshed.applicant_id
            },
            "property_2_application": {
                "id": prop2_app_refreshed.id,
                "property_id": prop2_app_refreshed.property_id,
                "status": prop2_app_refreshed.status.value,
                "applicant_id": prop2_app_refreshed.applicant_id
            }
        }

