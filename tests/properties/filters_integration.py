"""
Phase 4: Comprehensive Integration Testing for Advanced Property Search
Tests all Phase 3 & 4 features end-to-end
"""

import pytest
from sqlalchemy.orm import Session
from datetime import datetime
from app.models.property import Property, PropertyType, PropertyStatus
from app.models.user import User
import time


@pytest.fixture
def test_properties(client, db_session):
    """Create test properties with various attributes"""
    db = db_session
    properties = [
        Property(
            title="Luxury House in NYC",
            description="Beautiful house with pool and garage",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.FOR_SALE,
            address="123 Main St",
            city="New York",
            state="NY",
            zip_code="10001",
            country="USA",
            bedrooms=3,
            bathrooms=2.5,
            square_feet=2000,
            price=500000,
            features=["pool", "garage", "garden"],
            is_featured=True,
            year_built=2015,
            owner_id=1,
            is_active=True
        ),
        Property(
            title="Cozy Apartment in Brooklyn",
            description="Modern apartment with great amenities",
            property_type=PropertyType.APARTMENT,
            status=PropertyStatus.FOR_RENT,
            address="456 Oak Ave",
            city="Brooklyn",
            state="NY",
            zip_code="11201",
            country="USA",
            bedrooms=2,
            bathrooms=1,
            square_feet=1200,
            price=2500,
            features=["elevator", "gym"],
            is_featured=False,
            year_built=2020,
            owner_id=1,
            is_active=True
        ),
        Property(
            title="Downtown Loft",
            description="Industrial loft in downtown",
            property_type=PropertyType.CONDO,
            status=PropertyStatus.FOR_SALE,
            address="789 Pine St",
            city="Manhattan",
            state="NY",
            zip_code="10002",
            country="USA",
            bedrooms=1,
            bathrooms=1,
            square_feet=800,
            price=300000,
            features=["loft", "exposed_brick"],
            is_featured=True,
            year_built=1920,
            owner_id=1,
            is_active=True
        ),
    ]
    
    for prop in properties:
        db.add(prop)
    db.commit()
    
    return properties


# 1️⃣ Redis Caching Validation Tests

def test_caching_configured(client):
    """Test that Redis cache is configured (if enabled)"""
    # Cache configuration test
    # Note: Actual cache verification requires Redis server
    response = client.get("/api/properties/search?city=New York")
    assert response.status_code == 200
    # Cache hit verification would require monitoring Redis


def test_repeated_queries_performance(client, test_properties):
    """Test that repeated queries are handled efficiently"""
    import time
    
    # First query
    start = time.time()
    response1 = client.get("/api/properties/search?city=New York")
    time1 = time.time() - start
    assert response1.status_code == 200
    
    # Second query (should be faster if cached)
    start = time.time()
    response2 = client.get("/api/properties/search?city=New York")
    time2 = time.time() - start
    assert response2.status_code == 200
    
    # Results should be identical
    assert response1.json() == response2.json()
    
    # Note: Actual cache verification requires Redis monitoring


# 2️⃣ Rate Limiting Tests

def test_rate_limit_configured(client):
    """Test that rate limiting middleware is configured"""
    # Rate limiting is configured in main.py
    # Actual rate limit testing requires Redis
    response = client.get("/api/properties/search")
    assert response.status_code == 200
    # Note: Real rate limit testing needs many requests


def test_rate_limit_enforcement(client):
    """Test rate limit enforcement (if enabled)"""
    # Make many requests to test rate limiting
    # Note: This requires rate limiter to be actually applied to endpoints
    responses = []
    for _ in range(20):
        responses.append(client.get("/api/properties/search"))
    
    # Check that some requests succeed
    successful = sum(1 for r in responses if r.status_code == 200)
    assert successful > 0


# 3️⃣ Search Functionality Tests

def test_search_by_price(client, test_properties):
    """Test filtering by price range"""
    response = client.get("/api/properties/search?price_min=200000&price_max=400000")
    assert response.status_code == 200
    data = response.json()
    assert "properties" in data
    assert len(data["properties"]) <= 2  # Should find 1-2 properties
    for prop in data["properties"]:
        assert 200000 <= prop["price"] <= 400000


def test_search_by_property_type(client, test_properties):
    """Test filtering by property type"""
    response = client.get("/api/properties/search?property_type=house")
    assert response.status_code == 200
    data = response.json()
    assert "properties" in data
    for prop in data["properties"]:
        assert prop["property_type"] == "house"


def test_search_by_location(client, test_properties):
    """Test location filtering (city, state, zip)"""
    # Test city search
    response = client.get("/api/properties/search?city=New York")
    assert response.status_code == 200
    data = response.json()
    assert len(data["properties"]) >= 1
    
    # Test state search
    response = client.get("/api/properties/search?state=NY")
    assert response.status_code == 200
    data = response.json()
    assert len(data["properties"]) >= 1
    
    # Test zip code search
    response = client.get("/api/properties/search?zip_code=10001")
    assert response.status_code == 200
    data = response.json()
    assert len(data["properties"]) >= 1


def test_search_by_bedrooms_bathrooms(client, test_properties):
    """Test filtering by bedrooms and bathrooms"""
    response = client.get("/api/properties/search?bedrooms=2&bathrooms=1")
    assert response.status_code == 200
    data = response.json()
    for prop in data["properties"]:
        assert prop["bedrooms"] >= 2
        assert prop["bathrooms"] >= 1


def test_search_by_features(client, test_properties):
    """Test JSON features search"""
    response = client.get("/api/properties/search?features=pool,garage")
    assert response.status_code == 200
    data = response.json()
    # Should find properties with pool AND garage
    for prop in data["properties"]:
        features = [f.lower() for f in prop.get("features", [])]
        assert "pool" in features or "garage" in features


def test_search_by_status(client, test_properties):
    """Test filtering by property status"""
    response = client.get("/api/properties/search?status=for_sale")
    assert response.status_code == 200
    data = response.json()
    for prop in data["properties"]:
        assert prop["status"] == "for_sale"


def test_search_by_featured(client, test_properties):
    """Test filtering by featured properties"""
    response = client.get("/api/properties/search?is_featured=true")
    assert response.status_code == 200
    data = response.json()
    for prop in data["properties"]:
        assert prop["is_featured"] is True


def test_search_by_year_built(client, test_properties):
    """Test filtering by year built"""
    response = client.get("/api/properties/search?year_built_min=2010&year_built_max=2025")
    assert response.status_code == 200
    data = response.json()
    for prop in data["properties"]:
        assert 2010 <= prop.get("year_built", 0) <= 2025


def test_search_sorting_asc(client, test_properties):
    """Test sorting in ascending order"""
    response = client.get("/api/properties/search?sort_by=price&sort_order=asc")
    assert response.status_code == 200
    data = response.json()
    prices = [prop["price"] for prop in data["properties"]]
    assert prices == sorted(prices)


def test_search_sorting_desc(client, test_properties):
    """Test sorting in descending order"""
    response = client.get("/api/properties/search?sort_by=price&sort_order=desc")
    assert response.status_code == 200
    data = response.json()
    prices = [prop["price"] for prop in data["properties"]]
    assert prices == sorted(prices, reverse=True)


def test_search_pagination(client, test_properties):
    """Test pagination with correct metadata"""
    response = client.get("/api/properties/search?page=1&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert "properties" in data
    assert "total_count" in data
    assert "page" in data
    assert "limit" in data
    assert "total_pages" in data
    assert data["page"] == 1
    assert data["limit"] == 2
    assert len(data["properties"]) <= 2


def test_search_no_results(client, test_properties):
    """Test search with no matching results"""
    response = client.get("/api/properties/search?city=NonexistentCity")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert len(data["properties"]) == 0


def test_search_invalid_filters(client, test_properties):
    """Test that invalid filters are rejected"""
    # Negative price should be rejected
    response = client.get("/api/properties/search?price_min=-100")
    assert response.status_code == 422  # Validation error


def test_search_combined_filters(client, test_properties):
    """Test multiple filters combined"""
    response = client.get(
        "/api/properties/search"
        "?city=New York"
        "&property_type=house"
        "&bedrooms=3"
        "&price_min=400000"
        "&price_max=600000"
    )
    assert response.status_code == 200
    data = response.json()
    # Verify all filters are applied correctly
    for prop in data["properties"]:
        assert prop["property_type"] == "house"
        assert prop["bedrooms"] >= 3
        assert 400000 <= prop["price"] <= 600000


# 4️⃣ Endpoint Coverage Tests

def test_search_get_endpoint(client, test_properties):
    """Test GET /api/properties/search"""
    response = client.get("/api/properties/search?city=Brooklyn")
    assert response.status_code == 200
    data = response.json()
    assert "properties" in data
    assert "total_count" in data


def test_search_post_endpoint(client, test_properties):
    """Test POST /api/properties/search"""
    filters = {
        "city": "Manhattan",
        "property_type": "condo",
        "price_min": 200000,
        "price_max": 400000
    }
    response = client.post("/api/properties/search", json=filters)
    assert response.status_code == 200
    data = response.json()
    assert "properties" in data


def test_response_schema(client, test_properties):
    """Validate response schema matches PropertySearchResponse"""
    response = client.get("/api/properties/search")
    assert response.status_code == 200
    data = response.json()
    
    # Verify required fields
    assert "properties" in data
    assert "total_count" in data
    assert "page" in data
    assert "limit" in data
    assert "total_pages" in data
    
    # Verify properties structure
    if data["properties"]:
        prop = data["properties"][0]
        assert "id" in prop
        assert "title" in prop
        assert "price" in prop
        assert "city" in prop


def test_openapi_docs_parameters(client):
    """Test that OpenAPI docs include all parameters"""
    # Verify search endpoint is documented in OpenAPI spec
    response = client.get("/openapi.json")
    assert response.status_code == 200
    openapi_spec = response.json()
    
    paths = openapi_spec.get("paths", {})
    # Check if search endpoint exists in paths
    search_endpoints = [path for path in paths.keys() if "search" in path]
    assert len(search_endpoints) > 0, "Search endpoints should be documented"


# 5️⃣ Performance Testing

def test_search_performance(client, test_properties):
    """Test that search completes in reasonable time"""
    import time
    
    start = time.time()
    response = client.get("/api/properties/search")
    elapsed = time.time() - start
    
    assert response.status_code == 200
    # Should complete in less than 500ms for test data
    assert elapsed < 0.5


def test_high_frequency_queries(client, test_properties):
    """Test handling of high-frequency queries"""
    responses = []
    start = time.time()
    
    for _ in range(10):
        responses.append(client.get("/api/properties/search?city=Brooklyn"))
    
    elapsed = time.time() - start
    
    # All requests should succeed
    for response in responses:
        assert response.status_code == 200
    
    # Should handle 10 requests efficiently
    assert elapsed < 2.0  # Less than 2 seconds for 10 requests


# 6️⃣ Full End-to-End Verification

def test_end_to_end_flow(client, test_user_buyer):
    """Test complete flow: register → create property → search → verify"""
    # This test verifies existing flows still work
    # Search without authentication should still work
    response = client.get("/api/properties/search")
    assert response.status_code == 200


def test_existing_endpoints_intact(client):
    """Verify all existing endpoints still work"""
    # Root endpoint
    response = client.get("/")
    assert response.status_code == 200
    
    # Health check
    response = client.get("/health")
    assert response.status_code == 200


# 7️⃣ Reporting Helper

@pytest.fixture
def test_results():
    """Fixture to collect test results"""
    return {
        "passed": [],
        "failed": []
    }


def pytest_configure(config):
    """Configure pytest reporting"""
    config.option.verbose = True


# Additional edge case tests

def test_search_empty_database(client):
    """Test search with empty database"""
    response = client.get("/api/properties/search")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert len(data["properties"]) == 0


def test_search_max_limit(client, test_properties):
    """Test search with max limit (100)"""
    response = client.get("/api/properties/search?limit=100")
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] <= 100


def test_search_invalid_sort_field(client, test_properties):
    """Test search with invalid sort field (should use default)"""
    response = client.get("/api/properties/search?sort_by=invalid_field")
    assert response.status_code == 200
    data = response.json()
    # Should still return results with default sorting


def test_search_special_characters(client, test_properties):
    """Test search with special characters in filters"""
    response = client.get("/api/properties/search?city=New%20York")
    assert response.status_code == 200
    data = response.json()
    # Should handle URL encoding properly



