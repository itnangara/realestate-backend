"""
Seller endpoint tests
"""

import pytest


def test_create_seller(client, agent_headers):
    """Test creating seller"""
    seller_data = {
        "name": "John Doe",
        "age": 45,
        "is_old": False
    }
    
    response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "John Doe"
    assert data["age"] == 45
    assert data["is_old"] is False
    assert "id" in data
    assert "created_at" in data


def test_create_seller_unauthorized(client):
    """Test creating seller without authentication"""
    seller_data = {
        "name": "Unauthorized Seller",
        "age": 30
    }
    
    response = client.post("/api/sellers", json=seller_data)
    
    assert response.status_code == 401


def test_create_seller_minimal_data(client, agent_headers):
    """Test creating seller with minimal required data"""
    seller_data = {
        "name": "Jane Smith"
        # age and is_old are optional
    }
    
    response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Jane Smith"
    assert data["age"] is None
    assert data["is_old"] is False  # Default value


def test_get_all_sellers(client, agent_headers):
    """Test getting all sellers"""
    response = client.get("/api/sellers", headers=agent_headers)
    
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_all_sellers_unauthorized(client):
    """Test getting sellers without authentication"""
    response = client.get("/api/sellers")
    
    assert response.status_code == 401


def test_get_seller_by_id(client, agent_headers, db_session):
    """Test getting specific seller"""
    # First create a seller
    seller_data = {
        "name": "Test Seller",
        "age": 35,
        "is_old": False
    }
    
    create_response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    seller_id = create_response.json()["id"]
    
    # Get the seller
    response = client.get(f"/api/sellers/{seller_id}", headers=agent_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == seller_id
    assert data["name"] == "Test Seller"
    assert data["age"] == 35


def test_get_seller_nonexistent(client, agent_headers):
    """Test getting non-existent seller"""
    response = client.get("/api/sellers/99999", headers=agent_headers)
    
    assert response.status_code == 404
    assert "Seller not found" in response.json()["detail"]


def test_get_seller_unauthorized(client, agent_headers, db_session):
    """Test getting seller without authentication"""
    # Create a seller first
    seller_data = {"name": "Test Seller"}
    create_response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    seller_id = create_response.json()["id"]
    
    # Try to get without authentication
    response = client.get(f"/api/sellers/{seller_id}")
    
    assert response.status_code == 401


def test_update_seller(client, agent_headers, db_session):
    """Test updating seller"""
    # First create a seller
    seller_data = {
        "name": "Original Name",
        "age": 30,
        "is_old": False
    }
    
    create_response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    seller_id = create_response.json()["id"]
    
    # Update the seller
    update_data = {
        "name": "Updated Name",
        "age": 31,
        "is_old": True
    }
    
    response = client.put(f"/api/sellers/{seller_id}", json=update_data, headers=agent_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["age"] == 31
    assert data["is_old"] is True


def test_update_seller_partial(client, agent_headers, db_session):
    """Test partial seller update"""
    # First create a seller
    seller_data = {
        "name": "Partial Update Test",
        "age": 25,
        "is_old": False
    }
    
    create_response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    seller_id = create_response.json()["id"]
    
    # Update only name
    update_data = {"name": "Partially Updated"}
    
    response = client.put(f"/api/sellers/{seller_id}", json=update_data, headers=agent_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Partially Updated"
    assert data["age"] == 25  # Should remain unchanged
    assert data["is_old"] is False  # Should remain unchanged


def test_update_seller_nonexistent(client, agent_headers):
    """Test updating non-existent seller"""
    update_data = {
        "name": "Updated Name"
    }
    
    response = client.put("/api/sellers/99999", json=update_data, headers=agent_headers)
    
    assert response.status_code == 404
    assert "Seller not found" in response.json()["detail"]


def test_update_seller_unauthorized(client, agent_headers, db_session):
    """Test updating seller without authentication"""
    # Create a seller first
    seller_data = {"name": "Test Seller"}
    create_response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    seller_id = create_response.json()["id"]
    
    # Try to update without authentication
    update_data = {"name": "Unauthorized Update"}
    response = client.put(f"/api/sellers/{seller_id}", json=update_data)
    
    assert response.status_code == 401


def test_delete_seller(client, agent_headers, db_session):
    """Test deleting seller"""
    # First create a seller
    seller_data = {
        "name": "Seller to Delete",
        "age": 40
    }
    
    create_response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    seller_id = create_response.json()["id"]
    
    # Delete the seller
    response = client.delete(f"/api/sellers/{seller_id}", headers=agent_headers)
    
    assert response.status_code == 204


def test_delete_seller_nonexistent(client, agent_headers):
    """Test deleting non-existent seller"""
    response = client.delete("/api/sellers/99999", headers=agent_headers)
    
    assert response.status_code == 404
    assert "Seller not found" in response.json()["detail"]


def test_delete_seller_unauthorized(client, agent_headers, db_session):
    """Test deleting seller without authentication"""
    # Create a seller first
    seller_data = {"name": "Test Seller"}
    create_response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    seller_id = create_response.json()["id"]
    
    # Try to delete without authentication
    response = client.delete(f"/api/sellers/{seller_id}")
    
    assert response.status_code == 401


def test_seller_validation(client, agent_headers):
    """Test seller data validation"""
    # Test with invalid data
    invalid_seller_data = {
        "name": "",  # Empty name should fail
        "age": -5,  # Negative age should fail
        "is_old": "invalid"  # Should be boolean
    }
    
    response = client.post("/api/sellers", json=invalid_seller_data, headers=agent_headers)
    
    assert response.status_code == 422  # Validation error


def test_seller_name_validation(client, agent_headers):
    """Test seller name validation"""
    # Test with name too long
    long_name = "A" * 201  # Assuming max length is 200
    
    seller_data = {
        "name": long_name
    }
    
    response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    
    assert response.status_code == 422  # Validation error


def test_seller_age_validation(client, agent_headers):
    """Test seller age validation"""
    # Test with age out of range
    seller_data = {
        "name": "Valid Name",
        "age": 200  # Assuming max age is 150
    }
    
    response = client.post("/api/sellers", json=seller_data, headers=agent_headers)
    
    assert response.status_code == 422  # Validation error
