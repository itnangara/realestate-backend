"""
Application endpoint tests
"""

import pytest


def create_test_property(client, headers):
    """Helper function to create a test property"""
    property_data = {
        "title": "Test Property",
        "description": "Property for testing applications",
        "property_type": "house",
        "status": "for_sale",
        "address": "123 Test Street",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 400000
    }
    
    response = client.post("/api/properties", json=property_data, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def test_create_application(client, buyer_headers, db_session):
    """Test creating application"""
    # Create property first
    property_id = create_test_property(client, buyer_headers)
    
    application_data = {
        "property_id": property_id,
        "message": "I'm very interested in this property",
        "move_in_date": "2026-03-01T00:00:00Z",
        "lease_duration": 12,
        "annual_income": 75000,
        "credit_score": 750,
        "employment_status": "employed",
        "employer_name": "Test Company",
        "phone": "+1-555-0123",
        "alternate_email": "test@example.com",
        "documents_urls": [
            "https://example.com/pay_stub.pdf",
            "https://example.com/credit_report.pdf"
        ]
    }
    
    response = client.post("/api/applications", json=application_data, headers=buyer_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["property_id"] == property_id
    assert data["message"] == "I'm very interested in this property"
    assert data["status"] == "pending"
    assert data["applicant_id"] is not None


def test_create_application_unauthorized(client, buyer_headers):
    """Test creating application without authentication"""
    # Create property first using valid headers
    property_id = create_test_property(client, buyer_headers)
    
    application_data = {
        "property_id": property_id,
        "message": "Test application"
    }
    
    response = client.post("/api/applications", json=application_data)
    
    assert response.status_code == 401


def test_get_user_applications(client, buyer_headers):
    """Test getting user's applications"""
    response = client.get("/api/applications", headers=buyer_headers)
    
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_user_applications_unauthorized(client):
    """Test getting applications without authentication"""
    response = client.get("/api/applications")
    
    assert response.status_code == 401


def test_get_application_by_id(client, buyer_headers, db_session):
    """Test getting specific application"""
    # Create property first
    property_id = create_test_property(client, buyer_headers)
    
    # First create an application
    application_data = {
        "property_id": property_id,
        "message": "Test application for retrieval"
    }
    
    create_response = client.post("/api/applications", json=application_data, headers=buyer_headers)
    application_id = create_response.json()["id"]
    
    # Get the application
    response = client.get(f"/api/applications/{application_id}", headers=buyer_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == application_id
    assert data["message"] == "Test application for retrieval"


def test_get_application_nonexistent(client, buyer_headers):
    """Test getting non-existent application"""
    response = client.get("/api/applications/99999", headers=buyer_headers)
    
    assert response.status_code == 404
    assert "Application not found" in response.json()["detail"]


def test_get_application_unauthorized(client, buyer_headers, agent_headers, db_session):
    """Test getting application from different user"""
    # Create property first
    property_id = create_test_property(client, buyer_headers)
    
    # Create application as buyer
    application_data = {
        "property_id": property_id,
        "message": "Private application"
    }
    
    create_response = client.post("/api/applications", json=application_data, headers=buyer_headers)
    application_id = create_response.json()["id"]
    
    # Try to get as agent (should fail)
    response = client.get(f"/api/applications/{application_id}", headers=agent_headers)
    
    assert response.status_code == 403
    assert "Not enough permissions" in response.json()["detail"]


def test_update_application(client, buyer_headers, db_session):
    """Test updating application"""
    # Create property first
    property_id = create_test_property(client, buyer_headers)
    
    # First create an application
    application_data = {
        "property_id": property_id,
        "message": "Original message"
    }
    
    create_response = client.post("/api/applications", json=application_data, headers=buyer_headers)
    application_id = create_response.json()["id"]
    
    # Update the application
    update_data = {
        "message": "Updated message",
        "status": "under_review"
    }
    
    response = client.put(f"/api/applications/{application_id}", json=update_data, headers=buyer_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Updated message"
    assert data["status"] == "under_review"


def test_update_application_unauthorized(client, buyer_headers, agent_headers, db_session):
    """Test updating application from different user"""
    # Create property first
    property_id = create_test_property(client, buyer_headers)
    
    # Create application as buyer
    application_data = {
        "property_id": property_id,
        "message": "Original message"
    }
    
    create_response = client.post("/api/applications", json=application_data, headers=buyer_headers)
    application_id = create_response.json()["id"]
    
    # Try to update as agent (should fail)
    update_data = {"message": "Unauthorized update"}
    
    response = client.put(f"/api/applications/{application_id}", json=update_data, headers=agent_headers)
    
    assert response.status_code == 403
    assert "Not enough permissions" in response.json()["detail"]


def test_delete_application(client, buyer_headers, db_session):
    """Test deleting application"""
    # Create property first
    property_id = create_test_property(client, buyer_headers)
    
    # First create an application
    application_data = {
        "property_id": property_id,
        "message": "Application to delete"
    }
    
    create_response = client.post("/api/applications", json=application_data, headers=buyer_headers)
    application_id = create_response.json()["id"]
    
    # Delete the application
    response = client.delete(f"/api/applications/{application_id}", headers=buyer_headers)
    
    assert response.status_code == 204


def test_delete_application_unauthorized(client, buyer_headers, agent_headers, db_session):
    """Test deleting application from different user"""
    # Create property first
    property_id = create_test_property(client, buyer_headers)
    
    # Create application as buyer
    application_data = {
        "property_id": property_id,
        "message": "Application to delete"
    }
    
    create_response = client.post("/api/applications", json=application_data, headers=buyer_headers)
    application_id = create_response.json()["id"]
    
    # Try to delete as agent (should fail)
    response = client.delete(f"/api/applications/{application_id}", headers=agent_headers)
    
    assert response.status_code == 403
    assert "Not enough permissions" in response.json()["detail"]


def test_application_validation(client, buyer_headers):
    """Test application data validation"""
    # Test with invalid data
    invalid_application_data = {
        "property_id": "invalid",  # Should be integer
        "message": "",  # Should not be empty
        "credit_score": -100  # Should be positive
    }
    
    response = client.post("/api/applications", json=invalid_application_data, headers=buyer_headers)
    
    assert response.status_code == 422  # Validation error


def test_application_with_documents(client, buyer_headers):
    """Test application with document URLs"""
    # Create property first
    property_id = create_test_property(client, buyer_headers)
    
    application_data = {
        "property_id": property_id,
        "message": "Application with documents",
        "documents_urls": [
            "https://example.com/doc1.pdf",
            "https://example.com/doc2.pdf",
            "https://example.com/doc3.pdf"
        ]
    }
    
    response = client.post("/api/applications", json=application_data, headers=buyer_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert len(data["documents_urls"]) == 3
    assert "https://example.com/doc1.pdf" in data["documents_urls"]
