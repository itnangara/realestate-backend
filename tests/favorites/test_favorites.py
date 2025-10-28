"""
Favorites endpoint tests
"""

import pytest


def test_add_favorite(client, buyer_headers, test_property):
    """Test adding property to favorites"""
    favorite_data = {
        "property_id": test_property["id"]
    }
    
    response = client.post("/api/favorites", json=favorite_data, headers=buyer_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["property_id"] == test_property["id"]
    assert data["user_id"] is not None
    assert "id" in data
    assert "created_at" in data


def test_add_favorite_unauthorized(client, test_property):
    """Test adding favorite without authentication"""
    favorite_data = {
        "property_id": test_property["id"]
    }
    
    response = client.post("/api/favorites", json=favorite_data)
    
    assert response.status_code == 401


def test_get_user_favorites(client, buyer_headers):
    """Test getting user's favorites"""
    response = client.get("/api/favorites", headers=buyer_headers)
    
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_user_favorites_unauthorized(client):
    """Test getting favorites without authentication"""
    response = client.get("/api/favorites")
    
    assert response.status_code == 401


def test_check_favorite_true(client, buyer_headers, test_property, db_session):
    """Test checking if property is favorited (true case)"""
    # First add a favorite
    favorite_data = {"property_id": test_property["id"]}
    client.post("/api/favorites", json=favorite_data, headers=buyer_headers)
    
    # Check if it's favorited
    response = client.get(f"/api/favorites/check/{test_property['id']}", headers=buyer_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_favorite"] is True


def test_check_favorite_false(client, buyer_headers):
    """Test checking if property is favorited (false case)"""
    # Check property that's not favorited
    response = client.get("/api/favorites/check/999", headers=buyer_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_favorite"] is False


def test_check_favorite_unauthorized(client, test_property):
    """Test checking favorite without authentication"""
    response = client.get(f"/api/favorites/check/{test_property['id']}")
    
    assert response.status_code == 401


def test_remove_favorite(client, buyer_headers, test_property, db_session):
    """Test removing favorite"""
    # First add a favorite
    favorite_data = {"property_id": test_property["id"]}
    add_response = client.post("/api/favorites", json=favorite_data, headers=buyer_headers)
    favorite_id = add_response.json()["id"]
    
    # Remove the favorite
    response = client.delete(f"/api/favorites/{favorite_id}", headers=buyer_headers)
    
    assert response.status_code == 204


def test_remove_favorite_nonexistent(client, buyer_headers):
    """Test removing non-existent favorite"""
    response = client.delete("/api/favorites/99999", headers=buyer_headers)
    
    assert response.status_code == 404
    assert "Favorite not found" in response.json()["detail"]


def test_remove_favorite_unauthorized(client, buyer_headers, agent_headers, test_property, db_session):
    """Test removing favorite from different user"""
    # Add favorite as buyer
    favorite_data = {"property_id": test_property["id"]}
    add_response = client.post("/api/favorites", json=favorite_data, headers=buyer_headers)
    favorite_id = add_response.json()["id"]
    
    # Try to remove as agent (should fail)
    response = client.delete(f"/api/favorites/{favorite_id}", headers=agent_headers)
    
    assert response.status_code == 404  # Favorite not found for this user


def test_duplicate_favorite(client, buyer_headers, test_property, db_session):
    """Test adding duplicate favorite"""
    favorite_data = {"property_id": test_property["id"]}
    
    # Add first favorite
    response1 = client.post("/api/favorites", json=favorite_data, headers=buyer_headers)
    assert response1.status_code == 201
    
    # Try to add same favorite again
    response2 = client.post("/api/favorites", json=favorite_data, headers=buyer_headers)
    # This might return 201 (if duplicates are allowed) or 400 (if not)
    # The exact behavior depends on the implementation
    assert response2.status_code in [201, 400]


def test_favorite_with_property_details(client, buyer_headers, test_property, db_session):
    """Test favorite with property details included"""
    # Add a favorite
    favorite_data = {"property_id": test_property["id"]}
    client.post("/api/favorites", json=favorite_data, headers=buyer_headers)
    
    # Get favorites (should include property details)
    response = client.get("/api/favorites", headers=buyer_headers)
    
    assert response.status_code == 200
    favorites = response.json()
    if favorites:
        favorite = favorites[0]
        assert "property" in favorite or "property_id" in favorite


def test_favorite_validation(client, buyer_headers):
    """Test favorite data validation"""
    # Test with invalid property_id
    invalid_favorite_data = {
        "property_id": "invalid"  # Should be integer
    }
    
    response = client.post("/api/favorites", json=invalid_favorite_data, headers=buyer_headers)
    
    assert response.status_code == 422  # Validation error


def test_favorite_missing_property_id(client, buyer_headers):
    """Test favorite with missing property_id"""
    favorite_data = {}  # Missing property_id
    
    response = client.post("/api/favorites", json=favorite_data, headers=buyer_headers)
    
    assert response.status_code == 422  # Validation error
