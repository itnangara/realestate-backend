"""
Enterprise-grade test script for lease activation and auto-withdrawal logic.
Following RCA framework: Observe -> Instrument -> Analyze -> Fix -> Verify
"""

import sys
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.utils.database import SessionLocal
from app.models.application import Application, ApplicationStatus
from app.models.user import User
from app.models.property import Property
from app.models.role import Role
from app.models.user_role import UserRole
from app.services.application_service import ApplicationService
from app.core.logger import get_logger

logger = get_logger(__name__)

def setup_test_data(db: Session):
    """Create test users and properties"""
    print("\n[Setup] Setting up test data...")
    
    # Create test tenant
    tenant = db.query(User).filter(User.email == "test_tenant@example.com").first()
    if not tenant:
        tenant = User(
            email="test_tenant@example.com",
            username="test_tenant",
            first_name="Test",
            last_name="Tenant",
            hashed_password="test"
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        
        # Add tenant role
        role = db.query(Role).filter(Role.name == "tenant").first()
        if role:
            user_role = UserRole(user_id=tenant.id, role_id=role.id)
            db.add(user_role)
            db.commit()
    
    # Create test landlord
    landlord = db.query(User).filter(User.email == "test_landlord@example.com").first()
    if not landlord:
        landlord = User(
            email="test_landlord@example.com",
            username="test_landlord",
            first_name="Test",
            last_name="Landlord",
            hashed_password="test"
        )
        db.add(landlord)
        db.commit()
        db.refresh(landlord)
        
        # Add landlord role
        role = db.query(Role).filter(Role.name == "landlord").first()
        if role:
            user_role = UserRole(user_id=landlord.id, role_id=role.id)
            db.add(user_role)
            db.commit()
    
    # Create test properties
    property1 = db.query(Property).filter(Property.title == "Test Property 1").first()
    if not property1:
        property1 = Property(
            title="Test Property 1",
            property_type="apartment",
            listing_type="for_rent",
            status="active",
            price=1000,
            rent_price=1000,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            owner_id=landlord.id
        )
        db.add(property1)
        db.commit()
        db.refresh(property1)
    
    property2 = db.query(Property).filter(Property.title == "Test Property 2").first()
    if not property2:
        property2 = Property(
            title="Test Property 2",
            property_type="house",
            listing_type="for_rent",
            status="active",
            price=2000,
            rent_price=2000,
            address="456 Test Ave",
            city="Test City",
            state="TS",
            zip_code="12345",
            owner_id=landlord.id
        )
        db.add(property2)
        db.commit()
        db.refresh(property2)
    
    print(f"[OK] Test tenant ID: {tenant.id}")
    print(f"[OK] Test landlord ID: {landlord.id}")
    print(f"[OK] Test property 1 ID: {property1.id}")
    print(f"[OK] Test property 2 ID: {property2.id}")
    
    return tenant, landlord, property1, property2

def cleanup_test_data(db: Session, tenant_id: int):
    """Clean up test applications"""
    print("\n[Cleanup] Cleaning up test data...")
    db.query(Application).filter(Application.applicant_id == tenant_id).delete()
    db.commit()
    print("[OK] Test applications cleaned up")

def test_lease_signing_and_auto_withdrawal(db: Session, tenant_id: int, property1_id: int, property2_id: int):
    """Test 1: Sign lease and verify auto-withdrawal"""
    print("\n" + "="*60)
    print("TEST 1: Lease Signing and Auto-Withdrawal")
    print("="*60)
    
    # Clean up any existing applications first
    db.query(Application).filter(Application.applicant_id == tenant_id).delete()
    db.commit()
    
    service = ApplicationService(db)
    now = datetime.now(timezone.utc)
    
    # Create multiple applications
    print("\n[Creating] Creating 3 applications for tenant...")
    app1 = Application(
        applicant_id=tenant_id,
        property_id=property1_id,
        status=ApplicationStatus.APPROVED,
        message="Test application 1",
        updated_at=now
    )
    app2 = Application(
        applicant_id=tenant_id,
        property_id=property2_id,
        status=ApplicationStatus.PENDING,
        message="Test application 2",
        updated_at=now
    )
    app3 = Application(
        applicant_id=tenant_id,
        property_id=property1_id,
        status=ApplicationStatus.APPROVED,
        message="Test application 3",
        updated_at=now
    )
    db.add_all([app1, app2, app3])
    db.commit()
    db.refresh(app1)
    db.refresh(app2)
    db.refresh(app3)
    
    print(f"[OK] Created application 1 (APPROVED): ID {app1.id}")
    print(f"[OK] Created application 2 (PENDING): ID {app2.id}")
    print(f"[OK] Created application 3 (APPROVED): ID {app3.id}")
    
    # Sign lease for app1
    print(f"\n[Signing] Signing lease for application {app1.id}...")
    signed_app = service.sign_lease(application_id=app1.id)
    
    # Verify app1 is SIGNED
    assert signed_app.status == ApplicationStatus.SIGNED, f"Expected SIGNED, got {signed_app.status}"
    assert signed_app.lease_signed_at is not None, "lease_signed_at should be set"
    print(f"[OK] Application {app1.id} is now SIGNED")
    print(f"[OK] lease_signed_at: {signed_app.lease_signed_at}")
    
    # Verify other applications are withdrawn
    db.refresh(app2)
    db.refresh(app3)
    assert app2.status == ApplicationStatus.WITHDRAWN, f"Expected WITHDRAWN, got {app2.status}"
    assert app3.status == ApplicationStatus.WITHDRAWN, f"Expected WITHDRAWN, got {app3.status}"
    print(f"[OK] Application {app2.id} auto-withdrawn (was PENDING)")
    print(f"[OK] Application {app3.id} auto-withdrawn (was APPROVED)")
    
    # Cleanup
    db.query(Application).filter(Application.applicant_id == tenant_id).delete()
    db.commit()
    
    print("\n[PASS] TEST 1 PASSED: Lease signing and auto-withdrawal works correctly")
    return True

def test_cannot_sign_with_active_lease(db: Session, tenant_id: int, property1_id: int, property2_id: int):
    """Test 2: Cannot sign if tenant already has ACTIVE_LEASE"""
    print("\n" + "="*60)
    print("TEST 2: Prevent Signing with Active Lease")
    print("="*60)
    
    service = ApplicationService(db)
    now = datetime.now(timezone.utc)
    
    # Create active lease
    print("\n[Creating] Creating active lease...")
    active_lease = Application(
        applicant_id=tenant_id,
        property_id=property1_id,
        status=ApplicationStatus.ACTIVE_LEASE,
        message="Active lease",
        updated_at=now
    )
    db.add(active_lease)
    db.commit()
    db.refresh(active_lease)
    print(f"[OK] Created active lease: ID {active_lease.id}")
    
    # Create new approved application
    print("\n[Creating] Creating new approved application...")
    new_app = Application(
        applicant_id=tenant_id,
        property_id=property2_id,
        status=ApplicationStatus.APPROVED,
        message="New application",
        updated_at=now
    )
    db.add(new_app)
    db.commit()
    db.refresh(new_app)
    print(f"[OK] Created new application: ID {new_app.id}")
    
    # Try to sign - should fail
    print(f"\n[Testing] Attempting to sign application {new_app.id} (should fail)...")
    try:
        service.sign_lease(application_id=new_app.id)
        print("[FAIL] Should have raised HTTPException")
        return False
    except Exception as e:
        from fastapi import HTTPException
        if isinstance(e, HTTPException):
            error_detail = str(e.detail).lower() if isinstance(e.detail, str) else str(e.detail).lower()
            if "active lease" in error_detail or (isinstance(e.detail, dict) and "active lease" in str(e.detail.get("message", "")).lower()):
                print(f"[OK] Correctly prevented signing: {str(e.detail)[:100]}...")
            else:
                print(f"[FAIL] Expected 'active lease' error, got: {e.detail}")
                return False
        else:
            error_str = str(e).lower()
            if "active lease" in error_str:
                print(f"[OK] Correctly prevented signing: {str(e)[:100]}...")
            else:
                print(f"[FAIL] Expected 'active lease' error, got: {e}")
                return False
    
    # Cleanup
    db.delete(active_lease)
    db.delete(new_app)
    db.commit()
    
    print("\n[PASS] TEST 2 PASSED: Cannot sign when tenant has active lease")
    return True

def test_lease_activation(db: Session, tenant_id: int, property1_id: int):
    """Test 3: Activate lease from SIGNED to ACTIVE_LEASE"""
    print("\n" + "="*60)
    print("TEST 3: Lease Activation")
    print("="*60)
    
    # Clean up any existing applications first
    db.query(Application).filter(Application.applicant_id == tenant_id).delete()
    db.commit()
    
    service = ApplicationService(db)
    now = datetime.now(timezone.utc)
    
    # Create signed application
    print("\n[Creating] Creating signed application...")
    signed_app = Application(
        applicant_id=tenant_id,
        property_id=property1_id,
        status=ApplicationStatus.SIGNED,
        message="Signed application",
        lease_signed_at=now,
        updated_at=now
    )
    db.add(signed_app)
    db.commit()
    db.refresh(signed_app)
    print(f"[OK] Created signed application: ID {signed_app.id}")
    
    # Activate lease
    print(f"\n[Activating] Activating lease for application {signed_app.id}...")
    activated_app = service.activate_lease(application_id=signed_app.id)
    
    # Verify status
    assert activated_app.status == ApplicationStatus.ACTIVE_LEASE, f"Expected ACTIVE_LEASE, got {activated_app.status}"
    print(f"[OK] Application {signed_app.id} is now ACTIVE_LEASE")
    
    # Cleanup
    db.delete(activated_app)
    db.commit()
    
    print("\n[PASS] TEST 3 PASSED: Lease activation works correctly")
    return True

def test_cannot_activate_with_active_lease(db: Session, tenant_id: int, property1_id: int, property2_id: int):
    """Test 4: Cannot activate if tenant already has ACTIVE_LEASE"""
    print("\n" + "="*60)
    print("TEST 4: Prevent Activation with Active Lease")
    print("="*60)
    
    service = ApplicationService(db)
    now = datetime.now(timezone.utc)
    
    # Create active lease
    print("\n[Creating] Creating active lease...")
    active_lease = Application(
        applicant_id=tenant_id,
        property_id=property1_id,
        status=ApplicationStatus.ACTIVE_LEASE,
        message="Active lease",
        updated_at=now
    )
    db.add(active_lease)
    db.commit()
    db.refresh(active_lease)
    print(f"[OK] Created active lease: ID {active_lease.id}")
    
    # Create signed application
    print("\n[Creating] Creating signed application...")
    signed_app = Application(
        applicant_id=tenant_id,
        property_id=property2_id,
        status=ApplicationStatus.SIGNED,
        message="Signed application",
        lease_signed_at=now,
        updated_at=now
    )
    db.add(signed_app)
    db.commit()
    db.refresh(signed_app)
    print(f"[OK] Created signed application: ID {signed_app.id}")
    
    # Try to activate - should fail
    print(f"\n[Testing] Attempting to activate application {signed_app.id} (should fail)...")
    try:
        service.activate_lease(application_id=signed_app.id)
        print("[FAIL] Should have raised HTTPException")
        return False
    except Exception as e:
        from fastapi import HTTPException
        if isinstance(e, HTTPException):
            error_detail = str(e.detail).lower() if isinstance(e.detail, str) else str(e.detail).lower()
            if "active lease" in error_detail or (isinstance(e.detail, dict) and "active lease" in str(e.detail.get("message", "")).lower()):
                print(f"[OK] Correctly prevented activation: {str(e.detail)[:100]}...")
            else:
                print(f"[FAIL] Expected 'active lease' error, got: {e.detail}")
                return False
        else:
            error_str = str(e).lower()
            if "active lease" in error_str:
                print(f"[OK] Correctly prevented activation: {str(e)[:100]}...")
            else:
                print(f"[FAIL] Expected 'active lease' error, got: {e}")
                return False
    
    # Cleanup
    db.delete(active_lease)
    db.delete(signed_app)
    db.commit()
    
    print("\n[PASS] TEST 4 PASSED: Cannot activate when tenant has active lease")
    return True

def test_cannot_sign_non_approved(db: Session, tenant_id: int, property1_id: int):
    """Test 5: Cannot sign application that is not APPROVED"""
    print("\n" + "="*60)
    print("TEST 5: Prevent Signing Non-Approved Application")
    print("="*60)
    
    service = ApplicationService(db)
    now = datetime.now(timezone.utc)
    
    # Create pending application
    print("\n[Creating] Creating pending application...")
    pending_app = Application(
        applicant_id=tenant_id,
        property_id=property1_id,
        status=ApplicationStatus.PENDING,
        message="Pending application",
        updated_at=now
    )
    db.add(pending_app)
    db.commit()
    db.refresh(pending_app)
    print(f"[OK] Created pending application: ID {pending_app.id}")
    
    # Try to sign - should fail
    print(f"\n[Testing] Attempting to sign application {pending_app.id} (should fail)...")
    try:
        service.sign_lease(application_id=pending_app.id)
        print("[FAIL] Should have raised HTTPException")
        return False
    except Exception as e:
        from fastapi import HTTPException
        if isinstance(e, HTTPException):
            error_detail = str(e.detail).lower() if isinstance(e.detail, str) else str(e.detail).lower()
            if "approved" in error_detail or "status" in error_detail or (isinstance(e.detail, dict) and ("approved" in str(e.detail.get("message", "")).lower() or "status" in str(e.detail.get("message", "")).lower())):
                print(f"[OK] Correctly prevented signing non-approved: {str(e.detail)[:100]}...")
            else:
                print(f"[FAIL] Expected status/approved error, got: {e.detail}")
                return False
        else:
            error_str = str(e).lower()
            if "approved" in error_str or "status" in error_str:
                print(f"[OK] Correctly prevented signing non-approved: {str(e)[:100]}...")
            else:
                print(f"[FAIL] Expected status error, got: {e}")
                return False
    
    # Cleanup
    db.delete(pending_app)
    db.commit()
    
    print("\n[PASS] TEST 5 PASSED: Cannot sign non-approved application")
    return True

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("ENTERPRISE-GRADE LEASE ACTIVATION TEST SUITE")
    print("Following RCA Framework: Observe -> Instrument -> Analyze -> Verify")
    print("="*60)
    
    db = SessionLocal()
    test_results = []
    
    try:
        # Setup
        tenant, landlord, property1, property2 = setup_test_data(db)
        
        # Run tests
        print("\n" + "="*60)
        print("RUNNING ALL TESTS")
        print("="*60)
        
        test_results.append(("TEST 1: Lease Signing and Auto-Withdrawal", 
                            test_lease_signing_and_auto_withdrawal(db, tenant.id, property1.id, property2.id)))
        test_results.append(("TEST 2: Prevent Signing with Active Lease",
                            test_cannot_sign_with_active_lease(db, tenant.id, property1.id, property2.id)))
        test_results.append(("TEST 3: Lease Activation",
                            test_lease_activation(db, tenant.id, property1.id)))
        test_results.append(("TEST 4: Prevent Activation with Active Lease",
                            test_cannot_activate_with_active_lease(db, tenant.id, property1.id, property2.id)))
        test_results.append(("TEST 5: Prevent Signing Non-Approved",
                            test_cannot_sign_non_approved(db, tenant.id, property1.id)))
        
        # Cleanup
        cleanup_test_data(db, tenant.id)
        
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        passed = 0
        failed = 0
        for test_name, result in test_results:
            status = "[PASS]" if result else "[FAIL]"
            print(f"{status} {test_name}")
            if result:
                passed += 1
            else:
                failed += 1
        
        print("\n" + "="*60)
        if failed == 0:
            print("[SUCCESS] ALL TESTS PASSED!")
            print("="*60)
            print("\nEnterprise-grade lease activation logic is working correctly:")
            print("  [OK] Lease signing sets SIGNED status and lease_signed_at")
            print("  [OK] Auto-withdrawal of other applications works")
            print("  [OK] Cannot sign if tenant has ACTIVE_LEASE")
            print("  [OK] Lease activation works (SIGNED -> ACTIVE_LEASE)")
            print("  [OK] Cannot activate if tenant has ACTIVE_LEASE")
            print("  [OK] Cannot sign non-approved applications")
            print("="*60)
        else:
            print(f"[FAILED] {failed} test(s) failed, {passed} test(s) passed")
            print("="*60)
            sys.exit(1)
        
    except Exception as e:
        print(f"\n[ERROR] TEST SUITE FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()

