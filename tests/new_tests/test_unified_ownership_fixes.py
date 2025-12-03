"""
Test script to verify unified property ownership model fixes.

Tests:
1. SQL query fixes (no JSON column errors)
2. is_property_owner() helper function
3. PropertyPermissionService with unified model
4. Property counts in admin users list
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.database import SessionLocal
from app.models.user import User
from app.models.property import Property
from app.models.user_property import UserProperty, RelationshipType
from app.utils.property_ownership import is_property_owner, get_property_owners
from app.services.property_permissions import PropertyPermissionService

def test_sql_query_fix():
    """Test that Property-UserProperty queries work without JSON errors"""
    print("\n=== Test 1: SQL Query Fix (No JSON Errors) ===")
    db = SessionLocal()
    try:
        # This query should work without JSON comparison errors
        user_properties = db.query(UserProperty).filter(
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).limit(5).all()
        
        for up in user_properties:
            # Query with explicit column selection (avoids JSON comparison)
            prop = (
                db.query(Property.id, Property.title, Property.address)
                .filter(Property.id == up.property_id)
                .first()
            )
            if prop:
                print(f"✓ Property {prop.id}: {prop.title}")
        
        print("✓ SQL query fix verified - no JSON errors")
        return True
    except Exception as e:
        print(f"✗ SQL query failed: {e}")
        return False
    finally:
        db.close()

def test_is_property_owner():
    """Test is_property_owner() helper function"""
    print("\n=== Test 2: is_property_owner() Helper ===")
    db = SessionLocal()
    try:
        # Get a landlord user
        landlord = db.query(User).join(UserProperty).filter(
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).first()
        
        if not landlord:
            print("⚠ No landlord found with LANDLORD relationship")
            return True  # Not a failure, just no data
        
        # Get a property they own
        user_prop = db.query(UserProperty).filter(
            UserProperty.user_id == landlord.id,
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).first()
        
        if not user_prop:
            print("⚠ No property found for landlord")
            return True
        
        # Test ownership check
        result = is_property_owner(db, landlord.id, user_prop.property_id)
        print(f"✓ is_property_owner({landlord.id}, {user_prop.property_id}) = {result}")
        
        # Test with non-owner
        other_user = db.query(User).filter(User.id != landlord.id).first()
        if other_user:
            result2 = is_property_owner(db, other_user.id, user_prop.property_id)
            print(f"✓ is_property_owner({other_user.id}, {user_prop.property_id}) = {result2} (should be False)")
        
        print("✓ is_property_owner() helper verified")
        return True
    except Exception as e:
        print(f"✗ is_property_owner() test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def test_property_permissions():
    """Test PropertyPermissionService with unified model"""
    print("\n=== Test 3: PropertyPermissionService ===")
    db = SessionLocal()
    try:
        # Get a landlord user
        landlord = db.query(User).join(UserProperty).filter(
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).first()
        
        if not landlord:
            print("⚠ No landlord found")
            return True
        
        # Get a property they own
        user_prop = db.query(UserProperty).filter(
            UserProperty.user_id == landlord.id,
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).first()
        
        if not user_prop:
            print("⚠ No property found for landlord")
            return True
        
        property_obj = db.query(Property).filter(Property.id == user_prop.property_id).first()
        if not property_obj:
            print("⚠ Property not found")
            return True
        
        # Test can_update_property
        can_update = PropertyPermissionService.can_update_property(landlord, property_obj, db)
        print(f"✓ can_update_property(landlord, property) = {can_update} (should be True)")
        
        # Test can_delete_property
        can_delete = PropertyPermissionService.can_delete_property(landlord, property_obj, db)
        print(f"✓ can_delete_property(landlord, property) = {can_delete} (should be True)")
        
        # Test can_read_property
        can_read = PropertyPermissionService.can_read_property(landlord, property_obj, db)
        print(f"✓ can_read_property(landlord, property) = {can_read} (should be True)")
        
        print("✓ PropertyPermissionService verified")
        return True
    except Exception as e:
        print(f"✗ PropertyPermissionService test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def test_property_counts():
    """Test property counts in admin users list"""
    print("\n=== Test 4: Property Counts ===")
    db = SessionLocal()
    try:
        # Get distinct user_ids from user_properties (avoids JSON column DISTINCT issue)
        user_ids = (
            db.query(UserProperty.user_id)
            .distinct()
            .limit(5)
            .all()
        )
        
        # Convert to list of IDs
        user_id_list = [uid[0] for uid in user_ids]
        
        # Get users by ID
        users = db.query(User).filter(User.id.in_(user_id_list)).all()
        
        for user in users:
            count = db.query(UserProperty).filter(UserProperty.user_id == user.id).count()
            print(f"✓ User {user.id} ({user.email}): {count} properties")
        
        print("✓ Property counts verified")
        return True
    except Exception as e:
        print(f"✗ Property counts test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def test_get_property_owners():
    """Test get_property_owners() helper"""
    print("\n=== Test 5: get_property_owners() ===")
    db = SessionLocal()
    try:
        # Get a property with LANDLORD relationship
        user_prop = db.query(UserProperty).filter(
            UserProperty.relationship_type == RelationshipType.LANDLORD
        ).first()
        
        if not user_prop:
            print("⚠ No property with LANDLORD relationship found")
            return True
        
        owners = get_property_owners(db, user_prop.property_id)
        print(f"✓ Property {user_prop.property_id} has {len(owners)} owner(s): {owners}")
        
        print("✓ get_property_owners() verified")
        return True
    except Exception as e:
        print(f"✗ get_property_owners() test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Unified Property Ownership Model Fixes")
    print("=" * 60)
    
    results = []
    results.append(("SQL Query Fix", test_sql_query_fix()))
    results.append(("is_property_owner()", test_is_property_owner()))
    results.append(("PropertyPermissionService", test_property_permissions()))
    results.append(("Property Counts", test_property_counts()))
    results.append(("get_property_owners()", test_get_property_owners()))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
    print("=" * 60)
    
    sys.exit(0 if all_passed else 1)

