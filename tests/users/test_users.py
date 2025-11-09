"""
User endpoint tests
"""

import pytest


def test_get_current_user_profile(client, buyer_headers):
    """Test getting current user profile"""
    response = client.get("/api/users/me", headers=buyer_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "buyer@test.com"
    assert data["username"] == "buyer_user"
    assert data["first_name"] == "Test"
    assert data["last_name"] == "Buyer"
    assert "buyer" in data["roles"]


def test_update_user_profile(client, buyer_headers):
    """Test updating user profile"""
    update_data = {
        "first_name": "Updated",
        "last_name": "Buyer",
        "phone": "1234567890",
        "bio": "Updated bio"
    }
    
    response = client.put("/api/users/me", json=update_data, headers=buyer_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "Updated"
    assert data["last_name"] == "Buyer"
    assert data["phone"] == "1234567890"
    assert data["bio"] == "Updated bio"


def test_update_user_profile_partial(client, buyer_headers):
    """Test partial profile update"""
    update_data = {
        "phone": "9876543210"
    }
    
    response = client.put("/api/users/me", json=update_data, headers=buyer_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["phone"] == "9876543210"
    # Other fields should remain unchanged
    assert data["first_name"] == "Test"
    assert data["last_name"] == "Buyer"


def test_update_user_profile_unauthorized(client):
    """Test updating profile without authentication"""
    update_data = {
        "first_name": "Updated"
    }
    
    response = client.put("/api/users/me", json=update_data)
    
    assert response.status_code == 401


def test_deactivate_user_account(client, buyer_headers):
    """Test deactivating user account"""
    response = client.delete("/api/users/me", headers=buyer_headers)
    
    assert response.status_code == 204
    
    # Verify user is deactivated by trying to login
    login_response = client.post("/api/auth/login", data={
        "username": "buyer@test.com",
        "password": "testpassword"
    })
    
    assert login_response.status_code == 400
    assert "Inactive user" in login_response.json()["detail"]


def test_deactivate_user_unauthorized(client):
    """Test deactivating account without authentication"""
    response = client.delete("/api/users/me")
    
    assert response.status_code == 401


def test_update_user_roles_admin_success(client, admin_headers, test_user_buyer):
    """Test admin updating user roles"""
    roles_data = {
        "roles": ["buyer", "seller", "investor"]
    }
    
    response = client.put(f"/api/users/{test_user_buyer.id}/roles", 
                         json=roles_data, headers=admin_headers)
    
    assert response.status_code == 200
    updated_roles = response.json()
    assert set(updated_roles) == {"buyer", "seller", "investor"}


def test_update_user_roles_non_admin(client, buyer_headers, test_user_buyer):
    """Test non-admin trying to update roles"""
    roles_data = {
        "roles": ["seller"]
    }
    
    response = client.put(f"/api/users/{test_user_buyer.id}/roles", 
                         json=roles_data, headers=buyer_headers)
    
    assert response.status_code == 403
    assert "Only admins can modify user roles" in response.json()["detail"]


def test_update_user_roles_unauthorized(client, test_user_buyer):
    """Test updating roles without authentication"""
    roles_data = {
        "roles": ["seller"]
    }
    
    response = client.put(f"/api/users/{test_user_buyer.id}/roles", json=roles_data)
    
    assert response.status_code == 401


def test_update_user_roles_nonexistent_user(client, admin_headers):
    """Test updating roles for non-existent user"""
    roles_data = {
        "roles": ["seller"]
    }
    
    response = client.put("/api/users/99999/roles", json=roles_data, headers=admin_headers)
    
    assert response.status_code == 404
    assert "User with ID 99999 not found" in response.json()["detail"]


def test_update_user_roles_invalid_roles(client, admin_headers, test_user_buyer):
    """Test updating roles with invalid role names"""
    roles_data = {
        "roles": ["invalid_role", "another_invalid"]
    }
    
    response = client.put(f"/api/users/{test_user_buyer.id}/roles", 
                         json=roles_data, headers=admin_headers)
    
    assert response.status_code == 422
    response_data = response.json()
    # Pydantic v2 validation errors can be in different formats
    # Enterprise-grade: Handle validation errors gracefully without over-engineering
    if "detail" in response_data:
        error_detail = response_data["detail"]
        if isinstance(error_detail, list) and len(error_detail) > 0:
            error_msg = error_detail[0].get("msg", "")
            # Check for role validation error (either explicit message or value_error type)
            assert "Invalid role" in error_msg or "value_error" in str(error_detail).lower()
        else:
            # Fallback: check if detail is a string containing validation error
            error_str = str(error_detail).lower()
            assert "invalid role" in error_str or "value_error" in error_str
    else:
        # Handle edge case where response format differs (defensive but not over-engineered)
        response_str = str(response_data).lower()
        assert "invalid" in response_str or "validation" in response_str
