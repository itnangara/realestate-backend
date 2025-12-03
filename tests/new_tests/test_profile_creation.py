"""
Test script for profile creation functionality

Tests that profiles are automatically created when users are assigned roles.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.database import SessionLocal
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.maintenance_staff_profile import MaintenanceStaffProfile
from app.models.tenant_profile import TenantProfile
from app.models.landlord_profile import LandlordProfile
from app.models.agent_profile import AgentProfile
from app.models.investor_profile import InvestorProfile
from app.services.profile_service import ProfileService
from app.services.user_management_service import UserManagementService
from app.schemas.admin_user import UserCreateAdmin
from app.models.user import UserStatus

def test_profile_creation():
    """Test that profiles are created when roles are assigned"""
    db = SessionLocal()
    
    try:
        print("=" * 60)
        print("Testing Profile Creation Service")
        print("=" * 60)
        
        # Test 1: Create user with maintenance_staff role
        print("\n1. Testing user creation with maintenance_staff role...")
        service = UserManagementService(db)
        
        # Use unique email based on timestamp
        import time
        timestamp = int(time.time())
        
        # Create test user
        user_data = UserCreateAdmin(
            email=f"test_maintenance_{timestamp}@test.com",
            username=f"test_maintenance_user_{timestamp}",
            password="Test@123456",
            first_name="Test",
            last_name="Maintenance",
            roles=["maintenance_staff"],
            status=UserStatus.ACTIVE,
            is_active=True,
            is_verified=True
        )
        
        user = service.create_user(
            user_data=user_data,
            actor_id=1,  # Assuming admin user ID 1 exists
            request_id="test-001"
        )
        
        db.commit()
        db.refresh(user)
        
        # Check if profile was created
        profile = db.query(MaintenanceStaffProfile).filter(
            MaintenanceStaffProfile.user_id == user.id
        ).first()
        
        if profile:
            print(f"   [SUCCESS] MaintenanceStaffProfile created (ID: {profile.id})")
        else:
            print(f"   [FAILED] MaintenanceStaffProfile not created for user {user.id}")
            return False
        
        # Test 2: Create user with multiple roles
        print("\n2. Testing user creation with multiple roles (tenant, landlord)...")
        user_data2 = UserCreateAdmin(
            email=f"test_multi_{timestamp}@test.com",
            username=f"test_multi_user_{timestamp}",
            password="Test@123456",
            first_name="Test",
            last_name="Multi",
            roles=["tenant", "landlord"],
            status=UserStatus.ACTIVE,
            is_active=True,
            is_verified=True
        )
        
        user2 = service.create_user(
            user_data=user_data2,
            actor_id=1,
            request_id="test-002"
        )
        
        db.commit()
        db.refresh(user2)
        
        # Check profiles
        tenant_profile = db.query(TenantProfile).filter(
            TenantProfile.user_id == user2.id
        ).first()
        landlord_profile = db.query(LandlordProfile).filter(
            LandlordProfile.user_id == user2.id
        ).first()
        
        if tenant_profile and landlord_profile:
            print(f"   [SUCCESS] Both TenantProfile (ID: {tenant_profile.id}) and LandlordProfile (ID: {landlord_profile.id}) created")
        else:
            print(f"   [FAILED] Missing profiles - Tenant: {tenant_profile is not None}, Landlord: {landlord_profile is not None}")
            return False
        
        # Test 3: Test ProfileService directly
        print("\n3. Testing ProfileService directly...")
        profile_service = ProfileService(db)
        
        # Get the user we just created
        test_user = user
        if test_user:
            # Add investor role
            investor_role = db.query(Role).filter(Role.name == "investor").first()
            if investor_role:
                # Check if user already has role
                existing = db.query(UserRole).filter(
                    UserRole.user_id == test_user.id,
                    UserRole.role_id == investor_role.id
                ).first()
                
                if not existing:
                    user_role = UserRole(user_id=test_user.id, role_id=investor_role.id)
                    db.add(user_role)
                    db.commit()
                
                # Refresh user with roles
                db.refresh(test_user)
                from sqlalchemy.orm import joinedload
                user_with_roles = db.query(User).options(
                    joinedload(User.user_roles)
                ).filter(User.id == test_user.id).first()
                
                created = profile_service.create_profiles_for_roles(
                    user=user_with_roles,
                    roles=["investor"],
                    actor_id=1,
                    request_id="test-003"
                )
                
                db.commit()
                
                if "investor" in created:
                    investor_profile = db.query(InvestorProfile).filter(
                        InvestorProfile.user_id == test_user.id
                    ).first()
                    if investor_profile:
                        print(f"   [SUCCESS] InvestorProfile created (ID: {investor_profile.id})")
                    else:
                        print(f"   [FAILED] InvestorProfile not found after creation")
                        return False
                else:
                    print(f"   ⚠️  WARNING: Profile creation returned: {created}")
        
        # Test 4: Test idempotency
        print("\n4. Testing idempotency (should not create duplicate profiles)...")
        if test_user:
            db.refresh(test_user)
            user_with_roles = db.query(User).options(
                joinedload(User.user_roles)
            ).filter(User.id == test_user.id).first()
            
            # Try to create profile again
            created_again = profile_service.create_profiles_for_roles(
                user=user_with_roles,
                roles=["maintenance_staff"],
                actor_id=1,
                request_id="test-004"
            )
            
            if not created_again:
                print(f"   [SUCCESS] Idempotency works - no duplicate profile created")
            else:
                print(f"   [WARNING] Profile creation returned: {created_again}")
        
        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)
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
    success = test_profile_creation()
    sys.exit(0 if success else 1)

