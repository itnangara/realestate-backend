"""
Property endpoint tests
"""

import pytest


def test_get_properties(client):
    """Test getting properties list"""
    response = client.get("/api/properties")
    
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_properties_with_filters(client):
    """Test getting properties with filters"""
    response = client.get("/api/properties?city=New York&property_type=house&min_price=100000&max_price=500000")
    
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_properties_pagination(client):
    """Test properties pagination"""
    response = client.get("/api/properties?skip=0&limit=5")
    
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_property_by_id(client):
    """Test getting specific property"""
    # First get properties to find an ID
    properties_response = client.get("/api/properties")
    if properties_response.json():
        property_id = properties_response.json()[0]["id"]
        
        response = client.get(f"/api/properties/{property_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == property_id


def test_get_property_nonexistent(client):
    """Test getting non-existent property"""
    response = client.get("/api/properties/99999")
    
    assert response.status_code == 404
    assert "Property not found" in response.json()["detail"]


def test_create_property(client, agent_headers):
    """Test creating property"""
    property_data = {
        "title": "Beautiful Test House",
        "description": "A wonderful test property",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "draft",
        "address": "123 Test Street",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "country": "Test Country",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "bedrooms": 3,
        "bathrooms": 2.5,
        "square_feet": 2000,
        "lot_size": 0.5,
        "year_built": 2020,
        "price": 500000
    }
    
    response = client.post("/api/properties", json=property_data, headers=agent_headers)

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Beautiful Test House"
    assert data["property_type"] == "house"
    assert data["listing_type"] == "for_sale"
    assert data["status"] == "draft"
    assert data["price"] == 500000
    assert "id" in data
    assert "created_at" in data


def test_create_property_unauthorized(client):
    """Test creating property without authentication"""
    property_data = {
        "title": "Unauthorized Property",
        "description": "This should fail",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "draft",
        "address": "123 Test Street",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 300000
    }
    
    response = client.post("/api/properties", json=property_data)
    
    assert response.status_code == 401


def test_update_property(client, agent_headers, db_session):
    """Test updating property"""
    # First create a property
    property_data = {
        "title": "Original Title",
        "description": "Original description",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "draft",
        "address": "123 Test Street",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 400000
    }
    
    create_response = client.post("/api/properties", json=property_data, headers=agent_headers)
    property_id = create_response.json()["id"]
    
    # Update the property
    update_data = {
        "title": "Updated Title",
        "price": 450000
    }
    
    response = client.put(f"/api/properties/{property_id}", json=update_data, headers=agent_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["price"] == 450000


def test_update_property_unauthorized(client, agent_headers, buyer_headers, db_session):
    """Test updating property without ownership"""
    # Create property as agent
    property_data = {
        "title": "Agent Property",
        "description": "Agent's property",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "draft",
        "address": "123 Test Street",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 400000
    }
    
    create_response = client.post("/api/properties", json=property_data, headers=agent_headers)
    property_id = create_response.json()["id"]
    
    # Try to update as buyer (should fail)
    update_data = {"title": "Unauthorized Update"}
    
    response = client.put(f"/api/properties/{property_id}", json=update_data, headers=buyer_headers)
    
    assert response.status_code == 403
    assert "Not enough permissions" in response.json()["detail"]


def test_delete_property(client, agent_headers, db_session):
    """Test deleting property"""
    # First create a property
    property_data = {
        "title": "Property to Delete",
        "description": "This will be deleted",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "draft",
        "address": "123 Test Street",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 300000
    }
    
    create_response = client.post("/api/properties", json=property_data, headers=agent_headers)
    property_id = create_response.json()["id"]
    
    # Delete the property
    response = client.delete(f"/api/properties/{property_id}", headers=agent_headers)
    
    assert response.status_code == 204


def test_delete_property_unauthorized(client, agent_headers, buyer_headers, db_session):
    """Test deleting property without ownership"""
    # Create property as agent
    property_data = {
        "title": "Agent Property",
        "description": "Agent's property",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "draft",
        "address": "123 Test Street",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 400000
    }
    
    create_response = client.post("/api/properties", json=property_data, headers=agent_headers)
    property_id = create_response.json()["id"]
    
    # Try to delete as buyer (should fail)
    response = client.delete(f"/api/properties/{property_id}", headers=buyer_headers)
    
    assert response.status_code == 403
    assert "Not enough permissions" in response.json()["detail"]


def test_search_properties(client):
    """Test advanced property search"""
    search_filters = {
        "city": "New York",
        "property_type": "house",
        "price_min": 200000,
        "price_max": 800000,
        "bedrooms": 2
    }
    
    response = client.post("/api/properties/search", json=search_filters)
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "properties" in data
    assert "total_count" in data


def test_listing_type_filter_get(client, agent_headers, db_session):
    """Test filtering properties by listing_type using GET endpoint"""
    # Create properties with different listing types
    property_data_sale = {
        "title": "House for Sale",
        "description": "A house for sale",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "active",
        "address": "123 Sale St",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 500000
    }
    
    property_data_rent = {
        "title": "Apartment for Rent",
        "description": "An apartment for rent",
        "property_type": "apartment",
        "listing_type": "for_rent",
        "status": "active",
        "address": "456 Rent Ave",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "rent_price": 2000
    }
    
    client.post("/api/properties", json=property_data_sale, headers=agent_headers)
    client.post("/api/properties", json=property_data_rent, headers=agent_headers)
    
    # Test filtering by listing_type
    response = client.get("/api/properties?listing_type=for_sale")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        assert all(p.get("listing_type") == "for_sale" for p in data)
    
    response = client.get("/api/properties?listing_type=for_rent")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        assert all(p.get("listing_type") == "for_rent" for p in data)


def test_listing_type_filter_search_get(client, agent_headers, db_session):
    """Test filtering by listing_type in GET /api/properties/search"""
    # Create properties with different listing types
    property_data_sale = {
        "title": "House for Sale",
        "description": "A house for sale",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "active",
        "address": "123 Sale St",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 500000
    }
    
    property_data_rent = {
        "title": "Apartment for Rent",
        "description": "An apartment for rent",
        "property_type": "apartment",
        "listing_type": "for_rent",
        "status": "active",
        "address": "456 Rent Ave",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "rent_price": 2000
    }
    
    client.post("/api/properties", json=property_data_sale, headers=agent_headers)
    client.post("/api/properties", json=property_data_rent, headers=agent_headers)
    
    # Test GET search with listing_type filter
    response = client.get("/api/properties/search?listing_type=for_sale")
    assert response.status_code == 200
    data = response.json()
    assert "properties" in data
    assert "total_count" in data
    if data["properties"]:
        assert all(p.get("listing_type") == "for_sale" for p in data["properties"])


def test_listing_type_filter_search_post(client, agent_headers, db_session):
    """Test filtering by listing_type in POST /api/properties/search"""
    # Create properties with different listing types
    property_data_sale = {
        "title": "House for Sale",
        "description": "A house for sale",
        "property_type": "house",
        "listing_type": "for_sale",
        "status": "active",
        "address": "123 Sale St",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 500000
    }
    
    property_data_rent = {
        "title": "Apartment for Rent",
        "description": "An apartment for rent",
        "property_type": "apartment",
        "listing_type": "for_rent",
        "status": "active",
        "address": "456 Rent Ave",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "rent_price": 2000
    }
    
    client.post("/api/properties", json=property_data_sale, headers=agent_headers)
    client.post("/api/properties", json=property_data_rent, headers=agent_headers)
    
    # Test POST search with listing_type filter
    search_filters = {
        "listing_type": "for_sale"
    }
    response = client.post("/api/properties/search", json=search_filters)
    assert response.status_code == 200
    data = response.json()
    assert "properties" in data
    assert "total_count" in data
    if data["properties"]:
        assert all(p.get("listing_type") == "for_sale" for p in data["properties"])


def test_listing_type_all_values(client, agent_headers, db_session):
    """Test all listing_type enum values can be created"""
    listing_types = ["for_sale", "for_rent", "for_lease", "for_auction"]
    
    for listing_type in listing_types:
        property_data = {
            "title": f"Property {listing_type}",
            "description": f"A property {listing_type}",
            "property_type": "house",
            "listing_type": listing_type,
            "status": "draft",
            "address": f"123 {listing_type} St",
            "city": "Test City",
            "state": "TS",
            "zip_code": "12345",
            "price": 300000
        }
        
        response = client.post("/api/properties", json=property_data, headers=agent_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["listing_type"] == listing_type
