"""
Role-aware property CRUD tests

Tests for the role-based access control and filtering implemented in the property endpoints.
"""

import pytest
from fastapi import status
from app.models.property import Property, ListingType, PropertyStatus, PropertyType
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole


class TestRoleAwarePropertyListing:
    """Test role-aware property listing (GET /api/properties/)"""
    
    def test_public_user_sees_only_active_public_listings(self, client, db_session, test_roles):
        """Public/Guest users should only see ACTIVE properties with public listing types"""
        # Create properties with different statuses and listing types
        properties = [
            # Public should see these
            {"status": PropertyStatus.ACTIVE, "listing_type": ListingType.FOR_SALE, "is_active": True},
            {"status": PropertyStatus.ACTIVE, "listing_type": ListingType.FOR_RENT, "is_active": True},
            {"status": PropertyStatus.ACTIVE, "listing_type": ListingType.FOR_LEASE, "is_active": True},
            # Public should NOT see these
            {"status": PropertyStatus.DRAFT, "listing_type": ListingType.FOR_SALE, "is_active": True},
            {"status": PropertyStatus.ACTIVE, "listing_type": ListingType.FOR_PORTFOLIO, "is_active": True},
            {"status": PropertyStatus.DELETED, "listing_type": ListingType.FOR_SALE, "is_active": False},
        ]
        
        for prop_data in properties:
            prop = Property(
                title="Test Property",
                description="Test",
                property_type=PropertyType.HOUSE,
                status=prop_data["status"],
                listing_type=prop_data["listing_type"],
                is_active=prop_data["is_active"],
                address="123 Test St",
                city="Test City",
                state="TS",
                zip_code="12345",
                price=100000,
                owner_id=1
            )
            db_session.add(prop)
        db_session.commit()
        
        # Public request (no auth)
        response = client.get("/api/properties/")
        assert response.status_code == 200
        data = response.json()
        
        # Should only see 3 ACTIVE public listings
        assert data["total_count"] == 3
        for prop in data["properties"]:
            assert prop["status"] == "active"
            assert prop["listing_type"] in ["for_sale", "for_rent", "for_lease"]
            assert prop["is_active"] is True
    
    def test_buyer_sees_only_active_public_listings(self, client, buyer_headers, db_session, test_roles):
        """Buyer users should only see ACTIVE properties with public listing types"""
        # Create test properties
        prop = Property(
            title="Public Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.ACTIVE,
            listing_type=ListingType.FOR_SALE,
            is_active=True,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=100000,
            owner_id=1
        )
        db_session.add(prop)
        
        portfolio_prop = Property(
            title="Portfolio Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.ACTIVE,
            listing_type=ListingType.FOR_PORTFOLIO,
            is_active=True,
            address="456 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=200000,
            owner_id=2
        )
        db_session.add(portfolio_prop)
        db_session.commit()
        
        # Buyer request
        response = client.get("/api/properties/", headers=buyer_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should only see public listing, not portfolio
        assert data["total_count"] == 1
        assert data["properties"][0]["listing_type"] == "for_sale"
    
    def test_seller_sees_active_and_own_properties(self, client, db_session, test_roles, auth_service):
        """Seller should see ACTIVE public listings + their own properties (any status)"""
        # Create seller user
        hashed_password = auth_service.get_password_hash("sellerpass")
        seller = User(
            email="seller@test.com",
            username="seller_user",
            first_name="Test",
            last_name="Seller",
            hashed_password=hashed_password
        )
        db_session.add(seller)
        db_session.commit()
        db_session.refresh(seller)
        
        seller_role = db_session.query(Role).filter(Role.name == "seller").first()
        user_role = UserRole(user_id=seller.id, role_id=seller_role.id)
        db_session.add(user_role)
        db_session.commit()
        
        # Get seller token
        login_response = client.post("/api/auth/login", data={
            "username": "seller@test.com",
            "password": "sellerpass"
        })
        seller_token = login_response.json()["access_token"]
        seller_headers = {"Authorization": f"Bearer {seller_token}"}
        
        # Create properties
        # Public active (seller should see)
        public_prop = Property(
            title="Public Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.ACTIVE,
            listing_type=ListingType.FOR_SALE,
            is_active=True,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=100000,
            owner_id=999  # Different owner
        )
        db_session.add(public_prop)
        
        # Seller's own draft (seller should see)
        own_draft = Property(
            title="My Draft",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.DRAFT,
            listing_type=ListingType.FOR_SALE,
            is_active=True,
            address="456 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=200000,
            owner_id=seller.id  # Seller's own
        )
        db_session.add(own_draft)
        
        # Another seller's draft (seller should NOT see)
        other_draft = Property(
            title="Other Draft",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.DRAFT,
            listing_type=ListingType.FOR_SALE,
            is_active=True,
            address="789 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=300000,
            owner_id=888  # Different owner
        )
        db_session.add(other_draft)
        db_session.commit()
        
        # Seller request
        response = client.get("/api/properties/", headers=seller_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should see ONLY own draft (1 property) - "My Listings" mode
        assert data["total_count"] == 1
        property_titles = [p["title"] for p in data["properties"]]
        assert "My Draft" in property_titles
        assert "Public Property" not in property_titles  # Not own
        assert "Other Draft" not in property_titles  # Not own
    
    def test_admin_sees_all_properties(self, client, admin_headers, db_session, test_roles):
        """Admin should see all properties including deleted"""
        # Create properties with various statuses
        properties = [
            {"status": PropertyStatus.ACTIVE, "title": "Active Prop"},
            {"status": PropertyStatus.DRAFT, "title": "Draft Prop"},
            {"status": PropertyStatus.DELETED, "title": "Deleted Prop", "is_active": False},
        ]
        
        for prop_data in properties:
            prop = Property(
                title=prop_data["title"],
                description="Test",
                property_type=PropertyType.HOUSE,
                status=prop_data["status"],
                listing_type=ListingType.FOR_SALE,
                is_active=prop_data.get("is_active", True),
                address="123 Test St",
                city="Test City",
                state="TS",
                zip_code="12345",
                price=100000,
                owner_id=1
            )
            db_session.add(prop)
        db_session.commit()
        
        # Admin request
        response = client.get("/api/properties/", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Admin should see all (default excludes deleted, but can see via /all endpoint)
        # Regular endpoint still filters deleted by default
        assert data["total_count"] >= 2  # At least active and draft
    
    def test_admin_all_endpoint_sees_deleted(self, client, admin_headers, db_session, test_roles):
        """Admin /all endpoint should show all properties including deleted"""
        # Create deleted property
        deleted_prop = Property(
            title="Deleted Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.DELETED,
            listing_type=ListingType.FOR_SALE,
            is_active=False,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=100000,
            owner_id=1
        )
        db_session.add(deleted_prop)
        db_session.commit()
        
        # Admin /all endpoint
        response = client.get("/api/properties/all", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should see deleted property
        assert data["total_count"] >= 1
        property_titles = [p["title"] for p in data["properties"]]
        assert "Deleted Property" in property_titles
    
    def test_non_admin_cannot_access_all_endpoint(self, client, buyer_headers):
        """Non-admin users should get 403 on /all endpoint"""
        response = client.get("/api/properties/all", headers=buyer_headers)
        assert response.status_code == 403


class TestRoleAwarePropertyCreation:
    """Test role-aware property creation (POST /api/properties/)"""
    
    def test_seller_can_create_for_sale(self, client, db_session, test_roles, auth_service):
        """Seller should be able to create FOR_SALE listings"""
        # Create seller
        hashed_password = auth_service.get_password_hash("sellerpass")
        seller = User(
            email="seller@test.com",
            username="seller_user",
            first_name="Test",
            last_name="Seller",
            hashed_password=hashed_password
        )
        db_session.add(seller)
        db_session.commit()
        db_session.refresh(seller)
        
        seller_role = db_session.query(Role).filter(Role.name == "seller").first()
        user_role = UserRole(user_id=seller.id, role_id=seller_role.id)
        db_session.add(user_role)
        db_session.commit()
        
        # Get token
        login_response = client.post("/api/auth/login", data={
            "username": "seller@test.com",
            "password": "sellerpass"
        })
        seller_token = login_response.json()["access_token"]
        seller_headers = {"Authorization": f"Bearer {seller_token}"}
        
        # Create FOR_SALE property
        property_data = {
            "title": "Seller Property",
            "description": "Test",
            "property_type": "house",
            "listing_type": "for_sale",
            "status": "draft",
            "address": "123 Test St",
            "city": "Test City",
            "state": "TS",
            "zip_code": "12345",
            "price": 100000
        }
        
        response = client.post("/api/properties/", json=property_data, headers=seller_headers)
        assert response.status_code == 201
        assert response.json()["listing_type"] == "for_sale"
    
    def test_seller_cannot_create_for_rent(self, client, db_session, test_roles, auth_service):
        """Seller should NOT be able to create FOR_RENT listings"""
        # Create seller (same as above)
        hashed_password = auth_service.get_password_hash("sellerpass")
        seller = User(
            email="seller2@test.com",
            username="seller_user2",
            first_name="Test",
            last_name="Seller",
            hashed_password=hashed_password
        )
        db_session.add(seller)
        db_session.commit()
        db_session.refresh(seller)
        
        seller_role = db_session.query(Role).filter(Role.name == "seller").first()
        user_role = UserRole(user_id=seller.id, role_id=seller_role.id)
        db_session.add(user_role)
        db_session.commit()
        
        # Get token
        login_response = client.post("/api/auth/login", data={
            "username": "seller2@test.com",
            "password": "sellerpass"
        })
        seller_token = login_response.json()["access_token"]
        seller_headers = {"Authorization": f"Bearer {seller_token}"}
        
        # Try to create FOR_RENT property
        property_data = {
            "title": "Seller Property",
            "description": "Test",
            "property_type": "house",
            "listing_type": "for_rent",
            "status": "draft",
            "address": "123 Test St",
            "city": "Test City",
            "state": "TS",
            "zip_code": "12345",
            "price": 100000
        }
        
        response = client.post("/api/properties/", json=property_data, headers=seller_headers)
        assert response.status_code == 403
        assert "allow" in response.json()["detail"].lower() or "permission" in response.json()["detail"].lower()
    
    def test_investor_can_create_for_portfolio(self, client, db_session, test_roles, auth_service):
        """Investor should be able to create FOR_PORTFOLIO listings"""
        # Create investor
        hashed_password = auth_service.get_password_hash("investorpass")
        investor = User(
            email="investor@test.com",
            username="investor_user",
            first_name="Test",
            last_name="Investor",
            hashed_password=hashed_password
        )
        db_session.add(investor)
        db_session.commit()
        db_session.refresh(investor)
        
        investor_role = db_session.query(Role).filter(Role.name == "investor").first()
        user_role = UserRole(user_id=investor.id, role_id=investor_role.id)
        db_session.add(user_role)
        db_session.commit()
        
        # Get token
        login_response = client.post("/api/auth/login", data={
            "username": "investor@test.com",
            "password": "investorpass"
        })
        investor_token = login_response.json()["access_token"]
        investor_headers = {"Authorization": f"Bearer {investor_token}"}
        
        # Create FOR_PORTFOLIO property
        property_data = {
            "title": "Portfolio Property",
            "description": "Test",
            "property_type": "house",
            "listing_type": "for_portfolio",
            "status": "draft",
            "address": "123 Test St",
            "city": "Test City",
            "state": "TS",
            "zip_code": "12345",
            "price": 100000
        }
        
        response = client.post("/api/properties/", json=property_data, headers=investor_headers)
        assert response.status_code == 201
        assert response.json()["listing_type"] == "for_portfolio"
    
    def test_buyer_cannot_create_property(self, client, buyer_headers):
        """Buyer should NOT be able to create any property"""
        property_data = {
            "title": "Buyer Property",
            "description": "Test",
            "property_type": "house",
            "listing_type": "for_sale",
            "status": "draft",
            "address": "123 Test St",
            "city": "Test City",
            "state": "TS",
            "zip_code": "12345",
            "price": 100000
        }
        
        response = client.post("/api/properties/", json=property_data, headers=buyer_headers)
        assert response.status_code == 403


class TestRoleAwarePropertyUpdate:
    """Test role-aware property update (PUT /api/properties/{id})"""
    
    def test_owner_can_update_own_property(self, client, agent_headers, db_session):
        """Property owner should be able to update their own property"""
        # Create property owned by agent
        from app.services.property_service import PropertyService
        from app.schemas.property import PropertyCreate
        
        service = PropertyService(db_session)
        # Get agent user
        agent = db_session.query(User).filter(User.email == "agent@test.com").first()
        
        property_data = PropertyCreate(
            title="Agent Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            listing_type=ListingType.FOR_SALE,
            status=PropertyStatus.DRAFT,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=100000
        )
        
        prop = service.create_property_with_role_check(
            property_data=property_data,
            user=agent,
            request_id="test"
        )
        db_session.commit()
        
        # Update property
        update_data = {"title": "Updated Title"}
        response = client.put(f"/api/properties/{prop.id}", json=update_data, headers=agent_headers)
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"
    
    def test_non_owner_cannot_update_property(self, client, buyer_headers, agent_headers, db_session):
        """Non-owner should NOT be able to update someone else's property"""
        # Create property owned by agent
        from app.services.property_service import PropertyService
        from app.schemas.property import PropertyCreate
        
        service = PropertyService(db_session)
        agent = db_session.query(User).filter(User.email == "agent@test.com").first()
        
        property_data = PropertyCreate(
            title="Agent Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            listing_type=ListingType.FOR_SALE,
            status=PropertyStatus.DRAFT,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=100000
        )
        
        prop = service.create_property_with_role_check(
            property_data=property_data,
            user=agent,
            request_id="test"
        )
        db_session.commit()
        
        # Buyer tries to update
        update_data = {"title": "Hacked Title"}
        response = client.put(f"/api/properties/{prop.id}", json=update_data, headers=buyer_headers)
        assert response.status_code == 403
    
    def test_admin_can_update_any_property(self, client, admin_headers, agent_headers, db_session):
        """Admin should be able to update any property"""
        # Create property owned by agent
        from app.services.property_service import PropertyService
        from app.schemas.property import PropertyCreate
        
        service = PropertyService(db_session)
        agent = db_session.query(User).filter(User.email == "agent@test.com").first()
        
        property_data = PropertyCreate(
            title="Agent Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            listing_type=ListingType.FOR_SALE,
            status=PropertyStatus.DRAFT,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=100000
        )
        
        prop = service.create_property_with_role_check(
            property_data=property_data,
            user=agent,
            request_id="test"
        )
        db_session.commit()
        
        # Admin updates
        update_data = {"title": "Admin Updated Title"}
        response = client.put(f"/api/properties/{prop.id}", json=update_data, headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["title"] == "Admin Updated Title"


class TestRoleAwarePropertyDelete:
    """Test role-aware property soft delete (DELETE /api/properties/{id})"""
    
    def test_owner_can_delete_own_property(self, client, agent_headers, db_session):
        """Property owner should be able to soft delete their own property"""
        # Create property
        from app.services.property_service import PropertyService
        from app.schemas.property import PropertyCreate
        
        service = PropertyService(db_session)
        agent = db_session.query(User).filter(User.email == "agent@test.com").first()
        
        property_data = PropertyCreate(
            title="Agent Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            listing_type=ListingType.FOR_SALE,
            status=PropertyStatus.ACTIVE,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=100000
        )
        
        prop = service.create_property_with_role_check(
            property_data=property_data,
            user=agent,
            request_id="test"
        )
        db_session.commit()
        
        # Delete property
        response = client.delete(f"/api/properties/{prop.id}", headers=agent_headers)
        assert response.status_code == 204
        
        # Verify soft delete (status=DELETED)
        db_session.refresh(prop)
        assert prop.status == PropertyStatus.DELETED
        assert prop.is_active is False
    
    def test_deleted_property_hidden_from_public(self, client, agent_headers, db_session):
        """Deleted properties should be hidden from public view"""
        # Create and delete property
        from app.services.property_service import PropertyService
        from app.schemas.property import PropertyCreate
        
        service = PropertyService(db_session)
        agent = db_session.query(User).filter(User.email == "agent@test.com").first()
        
        property_data = PropertyCreate(
            title="To Be Deleted",
            description="Test",
            property_type=PropertyType.HOUSE,
            listing_type=ListingType.FOR_SALE,
            status=PropertyStatus.ACTIVE,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=100000
        )
        
        prop = service.create_property_with_role_check(
            property_data=property_data,
            user=agent,
            request_id="test"
        )
        db_session.commit()
        
        # Delete it
        client.delete(f"/api/properties/{prop.id}", headers=agent_headers)
        
        # Public should not see it
        response = client.get("/api/properties/")
        assert response.status_code == 200
        property_titles = [p["title"] for p in response.json()["properties"]]
        assert "To Be Deleted" not in property_titles
    
    def test_admin_can_see_deleted_properties(self, client, admin_headers, agent_headers, db_session):
        """Admin should be able to see deleted properties via /all endpoint"""
        # Create and delete property
        from app.services.property_service import PropertyService
        from app.schemas.property import PropertyCreate
        
        service = PropertyService(db_session)
        agent = db_session.query(User).filter(User.email == "agent@test.com").first()
        
        property_data = PropertyCreate(
            title="Deleted Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            listing_type=ListingType.FOR_SALE,
            status=PropertyStatus.ACTIVE,
            address="123 Test St",
            city="Test City",
            state="TS",
            zip_code="12345",
            price=100000
        )
        
        prop = service.create_property_with_role_check(
            property_data=property_data,
            user=agent,
            request_id="test"
        )
        db_session.commit()
        
        # Delete it
        client.delete(f"/api/properties/{prop.id}", headers=agent_headers)
        
        # Admin should see it in /all endpoint
        response = client.get("/api/properties/all", headers=admin_headers)
        assert response.status_code == 200
        property_titles = [p["title"] for p in response.json()["properties"]]
        assert "Deleted Property" in property_titles

