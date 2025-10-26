"""
Role management endpoint tests
"""

import pytest


def test_list_roles_admin(client, admin_headers):
    """Test listing roles as admin"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    assert isinstance(roles, list)
    assert len(roles) > 0
    
    # Check that expected roles are present
    role_names = [role["name"] for role in roles]
    assert "buyer" in role_names
    assert "seller" in role_names
    assert "agent" in role_names
    assert "landlord" in role_names
    assert "tenant" in role_names
    assert "investor" in role_names
    assert "admin" in role_names


def test_list_roles_non_admin(client, buyer_headers):
    """Test listing roles as non-admin user"""
    response = client.get("/api/roles", headers=buyer_headers)
    
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]


def test_list_roles_unauthorized(client):
    """Test listing roles without authentication"""
    response = client.get("/api/roles")
    
    assert response.status_code == 401


def test_list_roles_agent(client, agent_headers):
    """Test listing roles as agent (non-admin)"""
    response = client.get("/api/roles", headers=agent_headers)
    
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]


def test_roles_structure(client, admin_headers):
    """Test that roles have expected structure"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    if roles:
        role = roles[0]
        assert "id" in role
        assert "name" in role
        assert "description" in role
        assert isinstance(role["id"], int)
        assert isinstance(role["name"], str)
        assert isinstance(role["description"], (str, type(None)))


def test_roles_unique_names(client, admin_headers):
    """Test that role names are unique"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    role_names = [role["name"] for role in roles]
    assert len(role_names) == len(set(role_names)), "Role names should be unique"


def test_roles_expected_count(client, admin_headers):
    """Test that we have the expected number of roles"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    # Should have exactly 7 roles
    assert len(roles) == 7


def test_roles_admin_role_exists(client, admin_headers):
    """Test that admin role exists and has correct properties"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    admin_role = next((role for role in roles if role["name"] == "admin"), None)
    assert admin_role is not None, "Admin role should exist"
    
    assert admin_role["name"] == "admin"
    assert "administrator" in admin_role["description"].lower()


def test_roles_buyer_role_exists(client, admin_headers):
    """Test that buyer role exists and has correct properties"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    buyer_role = next((role for role in roles if role["name"] == "buyer"), None)
    assert buyer_role is not None, "Buyer role should exist"
    
    assert buyer_role["name"] == "buyer"
    assert "browse" in buyer_role["description"].lower() or "apply" in buyer_role["description"].lower()


def test_roles_agent_role_exists(client, admin_headers):
    """Test that agent role exists and has correct properties"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    agent_role = next((role for role in roles if role["name"] == "agent"), None)
    assert agent_role is not None, "Agent role should exist"
    
    assert agent_role["name"] == "agent"
    assert "professional" in agent_role["description"].lower()


def test_roles_landlord_role_exists(client, admin_headers):
    """Test that landlord role exists and has correct properties"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    landlord_role = next((role for role in roles if role["name"] == "landlord"), None)
    assert landlord_role is not None, "Landlord role should exist"
    
    assert landlord_role["name"] == "landlord"
    assert "rent" in landlord_role["description"].lower()


def test_roles_tenant_role_exists(client, admin_headers):
    """Test that tenant role exists and has correct properties"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    tenant_role = next((role for role in roles if role["name"] == "tenant"), None)
    assert tenant_role is not None, "Tenant role should exist"
    
    assert tenant_role["name"] == "tenant"
    assert "rent" in tenant_role["description"].lower()


def test_roles_investor_role_exists(client, admin_headers):
    """Test that investor role exists and has correct properties"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    investor_role = next((role for role in roles if role["name"] == "investor"), None)
    assert investor_role is not None, "Investor role should exist"
    
    assert investor_role["name"] == "investor"
    assert "invest" in investor_role["description"].lower()


def test_roles_seller_role_exists(client, admin_headers):
    """Test that seller role exists and has correct properties"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    seller_role = next((role for role in roles if role["name"] == "seller"), None)
    assert seller_role is not None, "Seller role should exist"
    
    assert seller_role["name"] == "seller"
    assert "sale" in seller_role["description"].lower()


def test_roles_response_format(client, admin_headers):
    """Test that roles response follows expected format"""
    response = client.get("/api/roles", headers=admin_headers)
    
    assert response.status_code == 200
    roles = response.json()
    
    # Should be a list
    assert isinstance(roles, list)
    
    # Each role should have required fields
    for role in roles:
        assert isinstance(role, dict)
        assert "id" in role
        assert "name" in role
        assert "description" in role
        assert isinstance(role["id"], int)
        assert isinstance(role["name"], str)
        assert isinstance(role["description"], (str, type(None)))
        assert role["id"] > 0
        assert len(role["name"]) > 0
