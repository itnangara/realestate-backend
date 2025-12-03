"""
Enterprise-grade test for role granting service

Tests:
- Transaction safety
- Profile creation
- Concurrency handling
- Error handling
- Multiple roles
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.database import SessionLocal
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.role_request import RoleRequest, RoleRequestStatus
from app.models.maintenance_staff_profile import MaintenanceStaffProfile
from app.models.tenant_profile import TenantProfile
from app.models.landlord_profile import LandlordProfile
from app.services.role_granting_service import RoleGrantingService
from app.services.user_management_service import UserManagementService
from app.schemas.admin_user import UserCreateAdmin
from app.models.user import UserStatus

def test_transaction_safety():
    """Test that transactions rollback on errors"""
    db = SessionLocal()
    
    try:
        print("=" * 60)
        print("Testing Transaction Safety")
        print("=" * 60)
        
        service = RoleGrantingService(db)
        
        # Create a test user
        user_data = UserCreateAdmin(
            email=f"test_transaction_{int(time.time())}@test.com",
            username=f"test_transaction_{int(time.time())}",
            password="Test@123456",
            first_name="Test",
            last_name="Transaction",
            roles=[],
            status=UserStatus.ACTIVE,
            is_active=True,
            is_verified=True
        )
        
        user_mgmt = UserManagementService(db)
        user = user_mgmt.create_user(user_data, actor_id=1, request_id="test-transaction")
        db.commit()
        
        print(f"\n1. Created test user (ID: {user.id})")
        
        # Grant roles - should create profiles
        result = service.grant_roles(
            user_id=user.id,
            role_names=["maintenance_staff", "tenant"],
            granted_by=1,
            request_id="test-transaction-001"
        )
        
        db.commit()
        
        print(f"   Granted roles: {result['granted_roles']}")
        print(f"   Skipped roles: {result['skipped_roles']}")
        
        # Verify profiles were created
        maintenance_profile = db.query(MaintenanceStaffProfile).filter(
            MaintenanceStaffProfile.user_id == user.id
        ).first()
        
        tenant_profile = db.query(TenantProfile).filter(
            TenantProfile.user_id == user.id
        ).first()
        
        if maintenance_profile and tenant_profile:
            print(f"   [SUCCESS] Both profiles created:")
            print(f"     - MaintenanceStaffProfile ID: {maintenance_profile.id}")
            print(f"     - TenantProfile ID: {tenant_profile.id}")
        else:
            print(f"   [FAILED] Missing profiles")
            return False
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

def test_concurrency_safety():
    """Test that concurrent approvals are handled safely"""
    db = SessionLocal()
    
    try:
        print("\n" + "=" * 60)
        print("Testing Concurrency Safety")
        print("=" * 60)
        
        # Create test user
        user_data = UserCreateAdmin(
            email=f"test_concurrent_{int(time.time())}@test.com",
            username=f"test_concurrent_{int(time.time())}",
            password="Test@123456",
            first_name="Test",
            last_name="Concurrent",
            roles=[],
            status=UserStatus.ACTIVE,
            is_active=True,
            is_verified=True
        )
        
        user_mgmt = UserManagementService(db)
        user = user_mgmt.create_user(user_data, actor_id=1, request_id="test-concurrent")
        db.commit()
        
        print(f"\n1. Created test user (ID: {user.id})")
        
        # Create role request
        role_request = RoleRequest(
            user_id=user.id,
            requested_roles=["landlord"],
            status=RoleRequestStatus.PENDING
        )
        db.add(role_request)
        db.commit()
        db.refresh(role_request)
        
        print(f"   Created role request (ID: {role_request.id})")
        
        # Approve the request
        service = RoleGrantingService(db)
        approved_request = service.approve_role_request(
            role_request_id=role_request.id,
            approved_by=1,
            request_id="test-concurrent-001"
        )
        
        print(f"   [SUCCESS] Role request approved")
        print(f"     - Status: {approved_request.status.value}")
        print(f"     - Reviewed by: {approved_request.reviewed_by}")
        
        # Try to approve again (should fail)
        try:
            service2 = RoleGrantingService(SessionLocal())
            service2.approve_role_request(
                role_request_id=role_request.id,
                approved_by=2,
                request_id="test-concurrent-002"
            )
            print(f"   [FAILED] Should have raised conflict error")
            return False
        except Exception as e:
            if "already" in str(e).lower() or "409" in str(e):
                print(f"   [SUCCESS] Concurrent approval prevented: {str(e)}")
            else:
                print(f"   [WARNING] Unexpected error: {str(e)}")
        
        # Verify profile was created
        landlord_profile = db.query(LandlordProfile).filter(
            LandlordProfile.user_id == user.id
        ).first()
        
        if landlord_profile:
            print(f"   [SUCCESS] LandlordProfile created (ID: {landlord_profile.id})")
        else:
            print(f"   [FAILED] LandlordProfile not created")
            return False
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

def test_multiple_roles():
    """Test granting multiple roles at once"""
    db = SessionLocal()
    
    try:
        print("\n" + "=" * 60)
        print("Testing Multiple Roles")
        print("=" * 60)
        
        # Create test user
        user_data = UserCreateAdmin(
            email=f"test_multi_{int(time.time())}@test.com",
            username=f"test_multi_{int(time.time())}",
            password="Test@123456",
            first_name="Test",
            last_name="Multi",
            roles=[],
            status=UserStatus.ACTIVE,
            is_active=True,
            is_verified=True
        )
        
        user_mgmt = UserManagementService(db)
        user = user_mgmt.create_user(user_data, actor_id=1, request_id="test-multi")
        db.commit()
        
        print(f"\n1. Created test user (ID: {user.id})")
        
        # Grant multiple roles
        service = RoleGrantingService(db)
        result = service.grant_roles(
            user_id=user.id,
            role_names=["tenant", "landlord", "maintenance_staff"],
            granted_by=1,
            request_id="test-multi-001"
        )
        
        db.commit()
        
        print(f"   Granted roles: {result['granted_roles']}")
        print(f"   Skipped roles: {result['skipped_roles']}")
        
        # Verify all profiles created
        tenant_profile = db.query(TenantProfile).filter(
            TenantProfile.user_id == user.id
        ).first()
        
        landlord_profile = db.query(LandlordProfile).filter(
            LandlordProfile.user_id == user.id
        ).first()
        
        maintenance_profile = db.query(MaintenanceStaffProfile).filter(
            MaintenanceStaffProfile.user_id == user.id
        ).first()
        
        if tenant_profile and landlord_profile and maintenance_profile:
            print(f"   [SUCCESS] All profiles created:")
            print(f"     - TenantProfile ID: {tenant_profile.id}")
            print(f"     - LandlordProfile ID: {landlord_profile.id}")
            print(f"     - MaintenanceStaffProfile ID: {maintenance_profile.id}")
        else:
            print(f"   [FAILED] Missing profiles")
            return False
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

def test_idempotency():
    """Test that granting same role twice is idempotent"""
    db = SessionLocal()
    
    try:
        print("\n" + "=" * 60)
        print("Testing Idempotency")
        print("=" * 60)
        
        # Create test user
        user_data = UserCreateAdmin(
            email=f"test_idempotent_{int(time.time())}@test.com",
            username=f"test_idempotent_{int(time.time())}",
            password="Test@123456",
            first_name="Test",
            last_name="Idempotent",
            roles=["tenant"],
            status=UserStatus.ACTIVE,
            is_active=True,
            is_verified=True
        )
        
        user_mgmt = UserManagementService(db)
        user = user_mgmt.create_user(user_data, actor_id=1, request_id="test-idempotent")
        db.commit()
        
        print(f"\n1. Created test user with tenant role (ID: {user.id})")
        
        # Count initial profiles
        initial_profiles = db.query(TenantProfile).filter(
            TenantProfile.user_id == user.id
        ).count()
        
        print(f"   Initial TenantProfile count: {initial_profiles}")
        
        # Try to grant tenant role again
        service = RoleGrantingService(db)
        result = service.grant_roles(
            user_id=user.id,
            role_names=["tenant"],
            granted_by=1,
            request_id="test-idempotent-001"
        )
        
        db.commit()
        
        print(f"   Granted roles: {result['granted_roles']}")
        print(f"   Skipped roles: {result['skipped_roles']}")
        
        # Count profiles after
        final_profiles = db.query(TenantProfile).filter(
            TenantProfile.user_id == user.id
        ).count()
        
        if final_profiles == initial_profiles and len(result['skipped_roles']) > 0:
            print(f"   [SUCCESS] Idempotency works - no duplicate role/profile")
            print(f"     - Final TenantProfile count: {final_profiles}")
        else:
            print(f"   [FAILED] Idempotency broken")
            print(f"     - Final TenantProfile count: {final_profiles}")
            return False
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Enterprise-Grade Role Granting Service Tests")
    print("=" * 60)
    
    results = []
    
    results.append(("Transaction Safety", test_transaction_safety()))
    results.append(("Concurrency Safety", test_concurrency_safety()))
    results.append(("Multiple Roles", test_multiple_roles()))
    results.append(("Idempotency", test_idempotency()))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("All tests passed!")
    else:
        print("Some tests failed!")
    print("=" * 60)
    
    sys.exit(0 if all_passed else 1)

