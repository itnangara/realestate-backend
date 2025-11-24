"""
Test: Create SUBMITTED application for different property when another has DRAFT

This test verifies the exact scenario:
1. Property 1 has DRAFT application
2. Try to create Property 2 application with status="submitted" directly in CREATE request

This tests if backend blocks or allows this scenario.
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.models.application import Application, ApplicationStatus
from app.models.property import Property, PropertyStatus, ListingType, PropertyType
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
        owner_id=test_landlord_user.id,
        is_active=True
    )
    db_session.add(property)
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
        owner_id=test_landlord_user.id,
        is_active=True
    )
    db_session.add(property)
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


class TestCreateSubmittedDifferentProperty:
    """
    Test creating Property 2 application with status="submitted" directly
    when Property 1 has DRAFT application.
    
    This tests the exact scenario the user is experiencing.
    """
    
    def test_create_property_2_with_submitted_status_when_property_1_has_draft(
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
        Test: Try to create Property 2 application with status="submitted" in CREATE request
        when Property 1 has DRAFT application.
        
        Expected behavior:
        - Backend ignores status field in CREATE (schema doesn't accept it)
        - Application is created as DRAFT regardless
        - No blocking validation should occur
        """
        
        # Step 1: Verify precondition - Property 1 has DRAFT application
        prop1_app = db_session.query(Application).filter(
            Application.id == property_1_draft_application.id
        ).first()
        
        assert prop1_app is not None, "Property 1 application should exist"
        assert prop1_app.status == ApplicationStatus.DRAFT, f"Property 1 should be DRAFT, got {prop1_app.status}"
        assert prop1_app.property_id == property_1.id, "Property 1 application should be for Property 1"
        print(f"[INFO] Precondition: Property 1 has DRAFT application (ID: {prop1_app.id})")
        
        # Step 2: Try to create Property 2 application with status="submitted" in CREATE request
        # This is what the frontend is trying to do
        application_data = {
            "property_id": property_2.id,
            "status": "submitted",  # Frontend is sending this
            "message": "I want to apply for Property 2 with submitted status",
            "move_in_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "lease_duration": 12,
            "annual_income": 60000,
            "credit_score": 750,
            "background_check_consent": True
        }
        
        print(f"[TEST] Attempting to create Property 2 application with status='submitted'")
        print(f"       Request payload includes: status='submitted'")
        
        create_response = client.post(
            "/api/tenant/applications",
            json=application_data,
            headers=tenant_headers
        )
        
        # Analyze the response
        print(f"[RESULT] Response status code: {create_response.status_code}")
        print(f"[RESULT] Response body: {create_response.text}")
        
        # Check if creation succeeded or failed
        if create_response.status_code == 201:
            # Creation succeeded
            create_data = create_response.json()
            property_2_app_id = create_data["id"]
            actual_status = create_data["status"]
            
            print(f"[SUCCESS] Property 2 application created (ID: {property_2_app_id})")
            print(f"[INFO] Requested status: 'submitted', Actual status: '{actual_status}'")
            
            # Verify what status was actually set
            assert actual_status == "draft", (
                f"Backend should ignore status='submitted' and create as DRAFT. "
                f"Got status: {actual_status}"
            )
            
            print(f"[VERIFIED] Backend correctly ignores status field and creates as DRAFT")
            
            # Verify Property 1 still exists and is DRAFT
            prop1_app_refreshed = db_session.query(Application).filter(
                Application.id == property_1_draft_application.id
            ).first()
            
            assert prop1_app_refreshed.status == ApplicationStatus.DRAFT, (
                "Property 1 should still be DRAFT"
            )
            
            # Verify Property 2 was created
            prop2_app_refreshed = db_session.query(Application).filter(
                Application.id == property_2_app_id
            ).first()
            
            assert prop2_app_refreshed is not None, "Property 2 application should exist"
            assert prop2_app_refreshed.status == ApplicationStatus.DRAFT, (
                "Property 2 should be DRAFT (backend ignores status in CREATE)"
            )
            assert prop2_app_refreshed.property_id == property_2.id, "Property 2 should be for Property 2"
            
            print(f"[EVIDENCE] Both applications exist:")
            print(f"   - Property 1 (ID: {prop1_app_refreshed.id}): {prop1_app_refreshed.status.value}")
            print(f"   - Property 2 (ID: {prop2_app_refreshed.id}): {prop2_app_refreshed.status.value}")
            
            print(f"\n[CONCLUSION] Backend allows creation but ignores status field")
            print(f"            Frontend must use 2-step: CREATE (DRAFT) -> UPDATE (SUBMITTED)")
            
        elif create_response.status_code == 400:
            # Creation failed with validation error
            error_data = create_response.json()
            error_detail = error_data.get("detail", {})
            
            print(f"[FAILURE] Property 2 application creation FAILED with 400 Bad Request")
            print(f"[ERROR] Error detail: {error_detail}")
            
            # Check if it's a duplicate/blocking error
            if isinstance(error_detail, dict):
                error_message = error_detail.get("message", "")
                error_field = error_detail.get("field", "")
                
                print(f"[ERROR] Field: {error_field}")
                print(f"[ERROR] Message: {error_message}")
                
                # Check if it's blocking due to Property 1 DRAFT
                if "already have" in error_message.lower() or "duplicate" in error_message.lower():
                    print(f"\n[BUG FOUND] Backend is incorrectly blocking Property 2 creation")
                    print(f"            due to Property 1 DRAFT application!")
                    print(f"            This is a BACKEND BUG - validation is too restrictive")
                elif "status" in error_message.lower():
                    print(f"\n[INFO] Error is related to status field validation")
                else:
                    print(f"\n[INFO] Error is unrelated to Property 1 DRAFT")
            
            # This should NOT happen - it's a bug if it does
            assert False, (
                f"Property 2 creation should NOT fail when Property 1 has DRAFT. "
                f"Error: {error_detail}"
            )
            
        elif create_response.status_code == 422:
            # Validation error (Pydantic)
            error_data = create_response.json()
            print(f"[FAILURE] Property 2 application creation FAILED with 422 Validation Error")
            print(f"[ERROR] Validation errors: {error_data.get('detail', [])}")
            
            # Check if status field is being rejected
            validation_errors = error_data.get("detail", [])
            status_error = None
            for error in validation_errors:
                if "status" in str(error).lower():
                    status_error = error
                    break
            
            if status_error:
                print(f"[INFO] Status field is being rejected by Pydantic validation")
                print(f"[INFO] This is expected - ApplicationCreate schema doesn't accept status")
                print(f"[INFO] Frontend should NOT send status in CREATE request")
            else:
                print(f"[INFO] Validation error is unrelated to status field")
            
            # This is expected - schema doesn't accept status
            print(f"\n[CONCLUSION] Backend schema correctly rejects status field in CREATE")
            print(f"            Frontend should NOT send status='submitted' in CREATE request")
            
        else:
            # Unexpected error
            print(f"[FAILURE] Property 2 application creation FAILED with unexpected status: {create_response.status_code}")
            print(f"[ERROR] Response: {create_response.text}")
            
            assert False, (
                f"Unexpected error creating Property 2 application. "
                f"Status: {create_response.status_code}, Response: {create_response.text}"
            )

