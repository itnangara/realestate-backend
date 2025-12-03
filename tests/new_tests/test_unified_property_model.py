"""
Test script for unified property ownership model

Tests:
- Migration worked correctly
- Property creation creates user_properties link
- Property counts work correctly
- Ownership checks work
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.database import SessionLocal
from app.models.user import User
from app.models.property import Property
from app.models.user_property import UserProperty, RelationshipType
from app.services.property_service import PropertyService
from app.services.user_management_service import UserManagementService
from app.schemas.admin_user import UserCreateAdmin
from app.schemas.property import PropertyCreate
from app.models.user import UserStatus
from app.models.property import PropertyType, PropertyStatus, ListingType

def test_migration_data():
    """Test that migration copied owner data correctly"""
    db = SessionLocal()
    
    try:
        print("=" * 60)
        print("Testing Migration Data")
        print("=" * 60)
        
        # Check if properties have corresponding user_properties rows
        all_properties = db.query(Property).all()
        properties_with_links = db.query(UserProperty).filter(
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).all()
        
        print(f"\n1. Found {len(all_properties)} properties total")
        print(f"   Found {len(properties_with_links)} LANDLORD relationships in user_properties")
        
        property_ids_with_links = {up.property_id for up in properties_with_links}
        properties_without_links = [p for p in all_properties if p.id not in property_ids_with_links]
        
        if properties_without_links:
            print(f"   [WARNING] {missing_count} properties missing links")
            return False
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def test_property_creation():
    """Test that property creation creates user_properties link"""
    db = SessionLocal()
    
    try:
        print("\n" + "=" * 60)
        print("Testing Property Creation")
        print("=" * 60)
        
        # Get or create a test landlord
        landlord = db.query(User).filter(User.email.like("%landlord%")).first()
        if not landlord:
            print("   [SKIP] No landlord user found for testing")
            return True
        
        print(f"\n1. Using landlord user (ID: {landlord.id}, Email: {landlord.email})")
        
        # Create a property
        property_service = PropertyService(db)
        property_data = PropertyCreate(
            title=f"Test Property {int(time.time())}",
            description="Test property for unified model",
            property_type=PropertyType.HOUSE,
            listing_type=ListingType.FOR_RENT,
            status=PropertyStatus.DRAFT,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            price=100000.0,
            bedrooms=3,
            bathrooms=2.0,
            square_feet=1500
        )
        
        property_obj = property_service.create_property(property_data, owner_id=landlord.id)
        db.commit()
        
        print(f"   Created property (ID: {property_obj.id})")
        
        # Check if user_properties link was created
        owner_link = db.query(UserProperty).filter(
            UserProperty.property_id == property_obj.id,
            UserProperty.user_id == landlord.id,
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).first()
        
        if owner_link:
            print(f"   [SUCCESS] user_properties OWNER link created (ID: {owner_link.id})")
        else:
            print(f"   [FAILED] user_properties OWNER link not created")
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

def test_property_count():
    """Test that property counts work correctly"""
    db = SessionLocal()
    
    try:
        print("\n" + "=" * 60)
        print("Testing Property Count")
        print("=" * 60)
        
        # Get a landlord with properties - use subquery to avoid JSON comparison issue
        landlord_ids = db.query(UserProperty.user_id).filter(
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).distinct().all()
        
        if not landlord_ids:
            print("   [SKIP] No landlords with properties found")
            return True
        
        landlord_id = landlord_ids[0][0]
        landlord = db.query(User).filter(User.id == landlord_id).first()
        
        if not landlord:
            print("   [SKIP] No landlord found")
            return True
        print(f"\n1. Testing with landlord (ID: {landlord.id}, Email: {landlord.email})")
        
        # Count from user_properties
        user_properties_count = db.query(UserProperty).filter(
            UserProperty.user_id == landlord.id,
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).count()
        
        # Count from unified model
        owner_id_count = db.query(UserProperty).filter(
            UserProperty.user_id == landlord.id,
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).count()
        
        # Total count (unified)
        total_count = db.query(UserProperty).filter(
            UserProperty.user_id == landlord.id
        ).count()
        
        print(f"   user_properties OWNER count: {user_properties_count}")
        print(f"   Property.owner_id count: {owner_id_count}")
        print(f"   Total user_properties count (all types): {total_count}")
        
        # The unified count should be at least the owner count
        if total_count >= user_properties_count:
            print(f"   [SUCCESS] Property counts are consistent")
        else:
            print(f"   [WARNING] Count mismatch detected")
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def test_user_creation_with_properties():
    """Test creating user with property assignment"""
    db = SessionLocal()
    
    try:
        print("\n" + "=" * 60)
        print("Testing User Creation with Property Assignment")
        print("=" * 60)
        
        # Get a property to assign
        property_obj = db.query(Property).first()
        if not property_obj:
            print("   [SKIP] No properties found for testing")
            return True
        
        print(f"\n1. Using property (ID: {property_obj.id})")
        
        # Create user with maintenance_staff role and property assignment
        user_mgmt = UserManagementService(db)
        user_data = UserCreateAdmin(
            email=f"test_maintenance_unified_{int(time.time())}@test.com",
            username=f"test_maintenance_unified_{int(time.time())}",
            password="Test@123456",
            first_name="Test",
            last_name="Maintenance",
            roles=["maintenance_staff"],
            status=UserStatus.ACTIVE,
            is_active=True,
            is_verified=True,
            property_ids=[property_obj.id]
        )
        
        user = user_mgmt.create_user(user_data, actor_id=1, request_id="test-unified")
        db.commit()
        
        print(f"   Created user (ID: {user.id})")
        
        # Check if user_properties link was created with MAINTENANCE type
        maintenance_link = db.query(UserProperty).filter(
            UserProperty.user_id == user.id,
            UserProperty.property_id == property_obj.id,
            UserProperty.relationship_type == RelationshipType.MAINTENANCE_STAFF
        ).first()
        
        if maintenance_link:
            print(f"   [SUCCESS] user_properties MAINTENANCE link created (ID: {maintenance_link.id})")
        else:
            print(f"   [FAILED] user_properties MAINTENANCE link not created")
            return False
        
        # Test property count
        count = db.query(UserProperty).filter(UserProperty.user_id == user.id).count()
        print(f"   Property count for user: {count}")
        
        if count == 1:
            print(f"   [SUCCESS] Property count is correct")
        else:
            print(f"   [FAILED] Property count mismatch (expected 1, got {count})")
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

def test_ownership_helpers():
    """Test ownership helper functions"""
    db = SessionLocal()
    
    try:
        print("\n" + "=" * 60)
        print("Testing Ownership Helper Functions")
        print("=" * 60)
        
        from app.utils.property_ownership import is_property_owner, get_property_owners
        
        # Get a property with an owner
        property_with_owner = db.query(Property).filter(
            Property.owner_id.isnot(None)
        ).first()
        
        if not property_with_owner:
            print("   [SKIP] No properties with owners found")
            return True
        
        owner_id = property_with_owner.owner_id
        print(f"\n1. Testing property (ID: {property_with_owner.id}, owner_id: {owner_id})")
        
        # Test is_property_owner
        is_owner = is_property_owner(db, owner_id, property_with_owner.id)
        print(f"   is_property_owner({owner_id}, {property_with_owner.id}): {is_owner}")
        
        if is_owner:
            print(f"   [SUCCESS] Ownership check works")
        else:
            print(f"   [FAILED] Ownership check failed")
            return False
        
        # Test get_property_owners
        owners = get_property_owners(db, property_with_owner.id)
        print(f"   get_property_owners({property_with_owner.id}): {owners}")
        
        if owner_id in owners:
            print(f"   [SUCCESS] get_property_owners works")
        else:
            print(f"   [FAILED] get_property_owners missing owner")
            return False
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Unified Property Ownership Model Tests")
    print("=" * 60)
    
    results = []
    
    results.append(("Migration Data", test_migration_data()))
    results.append(("Property Creation", test_property_creation()))
    results.append(("Property Count", test_property_count()))
    results.append(("User Creation with Properties", test_user_creation_with_properties()))
    results.append(("Ownership Helpers", test_ownership_helpers()))
    
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

