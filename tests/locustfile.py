"""
Load testing for Real Estate API using Locust
Tests performance under load with realistic user scenarios
"""

from locust import HttpUser, task, between
import random


class PropertySearchUser(HttpUser):
    """
    Simulates a user browsing and searching for properties
    """
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Called when a simulated user starts"""
        # Test health check first
        self.client.get("/health")
    
    @task(3)
    def search_properties(self):
        """Most common task: search properties with various filters"""
        filters = [
            # Popular searches
            "?city=New York&property_type=house",
            "?city=Brooklyn&bedrooms=2",
            "?price_min=100000&price_max=500000",
            "?is_featured=true",
            "?property_type=apartment&bathrooms=1",
            "?city=Boston&property_type=condo",
            "?status=for_rent&bedrooms=2",
            # Complex searches
            "?price_min=200000&price_max=800000&bedrooms=3&bathrooms=2",
            "?city=Manhattan&property_type=house&is_featured=true",
        ]
        
        # Pick a random filter
        self.client.get(f"/api/properties/search{random.choice(filters)}")
    
    @task(2)
    def get_property_details(self):
        """Get details of specific property"""
        # Assuming properties 1-10 exist (adjust based on your data)
        property_id = random.randint(1, 10)
        self.client.get(f"/api/properties/{property_id}")
    
    @task(1)
    def list_all_properties(self):
        """List all properties without filters"""
        self.client.get("/api/properties/search")
    
    @task(1)
    def health_check(self):
        """Check API health"""
        self.client.get("/health")
    
    @task(1)
    def get_api_docs(self):
        """Access API documentation"""
        self.client.get("/docs")
    
    @task(1)
    def root_endpoint(self):
        """Access root endpoint"""
        self.client.get("/")


class AuthenticatedUser(HttpUser):
    """
    Simulates an authenticated user with more permissions
    (Not implemented yet, but structure is ready)
    """
    wait_time = between(2, 5)
    
    def on_start(self):
        """Login and get token"""
        # Note: Would need actual credentials for full testing
        pass
    
    @task
    def get_my_profile(self):
        """Get current user profile"""
        self.client.get("/api/users/me")


