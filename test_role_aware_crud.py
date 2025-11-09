"""
Comprehensive test suite for Role-Aware Property CRUD system.

Tests all endpoints, permissions, and role-based filtering.
"""

import requests
import json
from typing import Dict, Optional

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api"

# Test users (will be created during tests)
test_users: Dict[str, Dict] = {
    "admin": {"email": "admin@test.com", "username": "adminuser", "password": "Admin123!", "first_name": "Admin", "last_name": "User", "roles": ["admin"]},
    "seller": {"email": "seller@test.com", "username": "selleruser", "password": "Seller123!", "first_name": "Seller", "last_name": "User", "roles": ["seller"]},
    "agent": {"email": "agent@test.com", "username": "agentuser", "password": "Agent123!", "first_name": "Agent", "last_name": "User", "roles": ["agent"]},
    "landlord": {"email": "landlord@test.com", "username": "landlorduser", "password": "Landlord123!", "first_name": "Landlord", "last_name": "User", "roles": ["landlord"]},
    "investor": {"email": "investor@test.com", "username": "investoruser", "password": "Investor123!", "first_name": "Investor", "last_name": "User", "roles": ["investor"]},
    "buyer": {"email": "buyer@test.com", "username": "buyeruser", "password": "Buyer123!", "first_name": "Buyer", "last_name": "User", "roles": ["buyer"]},
    "tenant": {"email": "tenant@test.com", "username": "tenantuser", "password": "Tenant123!", "first_name": "Tenant", "last_name": "User", "roles": ["tenant"]},
}

# Store tokens
tokens: Dict[str, str] = {}

# Store created property IDs
created_properties: Dict[str, int] = {}


def get_headers(user_type: Optional[str] = None) -> Dict[str, str]:
    """Get headers with optional authentication"""
    headers = {"Content-Type": "application/json"}
    if user_type and user_type in tokens:
        headers["Authorization"] = f"Bearer {tokens[user_type]}"
    return headers


def register_user(user_type: str) -> Dict:
    """Register a test user"""
    user_data = test_users[user_type]
    response = requests.post(
        f"{API_BASE}/auth/register",
        json=user_data,
        headers={"Content-Type": "application/json"}
    )
    print(f"\n{'='*60}")
    print(f"Registering {user_type} user...")
    print(f"Status: {response.status_code}")
    if response.status_code in [201, 409]:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Error: {response.text}")
    return response.json() if response.status_code in [200, 201, 409] else {}


def login_user(user_type: str) -> bool:
    """Login a test user and store token"""
    user_data = test_users[user_type]
    response = requests.post(
        f"{API_BASE}/auth/login",
        data={
            "username": user_data["email"],
            "password": user_data["password"]
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    print(f"\n{'='*60}")
    print(f"Logging in {user_type} user...")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        tokens[user_type] = data.get("access_token", "")
        print(f"Token received: {tokens[user_type][:20]}...")
        return True
    else:
        print(f"Error: {response.text}")
        return False


def create_property(user_type: str, property_data: Dict) -> Optional[Dict]:
    """Create a property as a specific user"""
    response = requests.post(
        f"{API_BASE}/properties/",
        json=property_data,
        headers=get_headers(user_type)
    )
    print(f"\n{'='*60}")
    print(f"Creating property as {user_type}...")
    print(f"Request: {json.dumps(property_data, indent=2)}")
    print(f"Status: {response.status_code}")
    if response.status_code == 201:
        data = response.json()
        created_properties[user_type] = data.get("id")
        print(f"Property created with ID: {data.get('id')}")
        print(f"Response: {json.dumps(data, indent=2)}")
        return data
    else:
        print(f"Error: {response.text}")
        return None


def get_properties(user_type: Optional[str] = None, params: Dict = None) -> Dict:
    """Get properties (public or authenticated)"""
    response = requests.get(
        f"{API_BASE}/properties/",
        params=params or {},
        headers=get_headers(user_type)
    )
    print(f"\n{'='*60}")
    print(f"Getting properties as {'public' if not user_type else user_type}...")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        # Handle both list and object responses
        if isinstance(data, list):
            print(f"Properties returned: {len(data)}")
            if data:
                print(f"First property: {json.dumps(data[0], indent=2)}")
            return {"properties": data, "total_count": len(data)}
        else:
            print(f"Total properties: {data.get('total_count', len(data.get('properties', [])))}")
            print(f"Properties returned: {len(data.get('properties', []))}")
            if data.get('properties'):
                print(f"First property: {json.dumps(data['properties'][0], indent=2)}")
            return data
    else:
        print(f"Error: {response.text}")
        return {}


def get_property_by_id(property_id: int, user_type: Optional[str] = None) -> Dict:
    """Get a specific property by ID"""
    response = requests.get(
        f"{API_BASE}/properties/{property_id}",
        headers=get_headers(user_type)
    )
    print(f"\n{'='*60}")
    print(f"Getting property {property_id} as {'public' if not user_type else user_type}...")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        return data
    else:
        print(f"Error: {response.text}")
        return {}


def update_property(property_id: int, user_type: str, update_data: Dict) -> Optional[Dict]:
    """Update a property as a specific user"""
    response = requests.put(
        f"{API_BASE}/properties/{property_id}",
        json=update_data,
        headers=get_headers(user_type)
    )
    print(f"\n{'='*60}")
    print(f"Updating property {property_id} as {user_type}...")
    print(f"Request: {json.dumps(update_data, indent=2)}")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        return data
    else:
        print(f"Error: {response.text}")
        return None


def delete_property(property_id: int, user_type: str) -> bool:
    """Delete a property as a specific user"""
    response = requests.delete(
        f"{API_BASE}/properties/{property_id}",
        headers=get_headers(user_type)
    )
    print(f"\n{'='*60}")
    print(f"Deleting property {property_id} as {user_type}...")
    print(f"Status: {response.status_code}")
    if response.status_code == 204:
        print("Property deleted successfully (soft delete)")
        return True
    else:
        print(f"Error: {response.text}")
        return False


def get_all_properties_admin(user_type: str) -> Dict:
    """Get all properties as admin"""
    response = requests.get(
        f"{API_BASE}/properties/all",
        headers=get_headers(user_type)
    )
    print(f"\n{'='*60}")
    print(f"Getting all properties as {user_type} (admin endpoint)...")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Total properties: {data.get('total_count', 0)}")
        print(f"Properties returned: {len(data.get('properties', []))}")
        return data
    else:
        print(f"Error: {response.text}")
        return {}


def run_tests():
    """Run comprehensive test suite"""
    print("\n" + "="*60)
    print("ROLE-AWARE PROPERTY CRUD TEST SUITE")
    print("="*60)
    
    # Test 1: Register all users
    print("\n\n### TEST 1: User Registration ###")
    for user_type in test_users.keys():
        register_user(user_type)
    
    # Test 2: Login all users
    print("\n\n### TEST 2: User Login ###")
    for user_type in test_users.keys():
        login_user(user_type)
    
    # Test 3: Create properties with different roles
    print("\n\n### TEST 3: Property Creation with Role Restrictions ###")
    
    # Seller creates for_sale property
    seller_property = create_property("seller", {
        "title": "Seller's House",
        "description": "A house for sale",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "active",
        "address": "123 Seller St",
        "city": "New York",
        "state": "NY",
        "zip_code": "10001",
        "country": "USA",
        "bedrooms": 3,
        "bathrooms": 2,
        "square_feet": 1800,
        "price": 500000
    })
    
    # Agent creates for_rent property
    agent_property = create_property("agent", {
        "title": "Agent's Rental",
        "description": "A rental property",
        "property_type": "apartment",
        "listing_type": "for_rent",
        "status": "active",
        "address": "456 Agent Ave",
        "city": "New York",
        "state": "NY",
        "zip_code": "10002",
        "country": "USA",
        "bedrooms": 2,
        "bathrooms": 1,
        "square_feet": 1200,
        "rent_price": 2500
    })
    
    # Landlord creates for_rent property
    landlord_property = create_property("landlord", {
        "title": "Landlord's Rental",
        "description": "Another rental",
        "property_type": "house",
        "listing_type": "for_rent",
        "status": "active",
        "address": "789 Landlord Ln",
        "city": "New York",
        "state": "NY",
        "zip_code": "10003",
        "country": "USA",
        "bedrooms": 4,
        "bathrooms": 3,
        "square_feet": 2400,
        "rent_price": 3500
    })
    
    # Investor creates for_portfolio property
    investor_property = create_property("investor", {
        "title": "Investor's Portfolio",
        "description": "Portfolio property",
        "property_type": "commercial",
        "listing_type": "for_portfolio",
        "status": "active",
        "address": "321 Investor Blvd",
        "city": "New York",
        "state": "NY",
        "zip_code": "10004",
        "country": "USA",
        "bedrooms": 0,
        "bathrooms": 2,
        "square_feet": 5000,
        "price": 2000000
    })
    
    # Test 4: Test permission violations
    print("\n\n### TEST 4: Permission Violations ###")
    
    # Seller tries to create for_rent (should fail)
    create_property("seller", {
        "title": "Seller's Rental Attempt",
        "property_type": "house",
        "listing_type": "for_rent",
        "status": "draft",
        "address": "999 Test St",
        "city": "New York",
        "state": "NY",
        "zip_code": "10005",
        "country": "USA",
        "price": 100000
    })
    
    # Buyer tries to create property (should fail)
    create_property("buyer", {
        "title": "Buyer's Attempt",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "draft",
        "address": "888 Test St",
        "city": "New York",
        "state": "NY",
        "zip_code": "10006",
        "country": "USA",
        "price": 100000
    })
    
    # Test 5: Public visibility (should not see FOR_PORTFOLIO)
    print("\n\n### TEST 5: Public Visibility (No Auth) ###")
    public_properties = get_properties(None)
    
    # Test 6: Buyer visibility (should not see FOR_PORTFOLIO)
    print("\n\n### TEST 6: Buyer Visibility ###")
    buyer_properties = get_properties("buyer")
    
    # Test 7: Get specific property (public)
    if seller_property and seller_property.get("id"):
        print("\n\n### TEST 7: Get Specific Property (Public) ###")
        get_property_by_id(seller_property["id"], None)
    
    # Test 8: Try to access FOR_PORTFOLIO as public (should fail)
    if investor_property and investor_property.get("id"):
        print("\n\n### TEST 8: Public Access to FOR_PORTFOLIO (Should Fail) ###")
        get_property_by_id(investor_property["id"], None)
    
    # Test 9: Owner can see their own FOR_PORTFOLIO
    if investor_property and investor_property.get("id"):
        print("\n\n### TEST 9: Owner Can See Own FOR_PORTFOLIO ###")
        get_property_by_id(investor_property["id"], "investor")
    
    # Test 10: Update property (owner)
    if seller_property and seller_property.get("id"):
        print("\n\n### TEST 10: Update Property (Owner) ###")
        update_property(seller_property["id"], "seller", {
            "title": "Updated Seller's House",
            "price": 550000
        })
    
    # Test 11: Update property (non-owner - should fail)
    if seller_property and seller_property.get("id"):
        print("\n\n### TEST 11: Update Property (Non-Owner - Should Fail) ###")
        update_property(seller_property["id"], "agent", {
            "title": "Unauthorized Update",
            "price": 999999
        })
    
    # Test 12: Admin can update any property
    if seller_property and seller_property.get("id"):
        print("\n\n### TEST 12: Admin Can Update Any Property ###")
        update_property(seller_property["id"], "admin", {
            "title": "Admin Updated Property",
            "price": 600000
        })
    
    # Test 13: Delete property (owner)
    if landlord_property and landlord_property.get("id"):
        print("\n\n### TEST 13: Delete Property (Owner - Soft Delete) ###")
        delete_property(landlord_property["id"], "landlord")
    
    # Test 14: Verify soft delete (property should not appear in public list)
    print("\n\n### TEST 14: Verify Soft Delete (Public Should Not See Deleted) ###")
    get_properties(None)
    
    # Test 15: Admin can see deleted properties
    print("\n\n### TEST 15: Admin Can See Deleted Properties ###")
    get_all_properties_admin("admin")
    
    # Test 16: Admin endpoint (non-admin should fail)
    print("\n\n### TEST 16: Admin Endpoint (Non-Admin - Should Fail) ###")
    get_all_properties_admin("seller")
    
    print("\n\n" + "="*60)
    print("TEST SUITE COMPLETE")
    print("="*60)


if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"\n\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()

