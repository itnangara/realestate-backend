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
        "status": "for_sale",
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
    assert data["status"] == "for_sale"
    assert data["price"] == 500000
    assert "id" in data
    assert "created_at" in data


def test_create_property_unauthorized(client):
    """Test creating property without authentication"""
    property_data = {
        "title": "Unauthorized Property",
        "description": "This should fail",
        "property_type": "house",
        "status": "for_sale",
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
        "status": "for_sale",
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
        "status": "for_sale",
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
        "status": "for_sale",
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
        "status": "for_sale",
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


def test_get_user_properties(client, agent_headers, db_session):
    """Test getting user's properties"""
    # Create a property first
    property_data = {
        "title": "User Property",
        "description": "User's property",
        "property_type": "house",
        "status": "for_sale",
        "address": "123 Test Street",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 350000
    }
    
    client.post("/api/properties", json=property_data, headers=agent_headers)
    
    # Get user properties (using agent's user ID)
    response = client.get("/api/properties/user/1")  # Assuming agent is user ID 1
    
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_search_properties(client):
    """Test advanced property search"""
    search_filters = {
        "city": "New York",
        "property_type": "house",
        "min_price": 200000,
        "max_price": 800000,
        "min_bedrooms": 2,
        "max_bedrooms": 4
    }
    
    response = client.post("/api/properties/search", json=search_filters)
    
    assert response.status_code == 200
    assert isinstance(response.json(), list)
