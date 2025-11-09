"""
Comprehensive Role-Aware Property Endpoint Tests

Tests all role-aware scenarios as specified in the requirements.
"""

import pytest
from fastapi import status
from app.models.property import Property, ListingType, PropertyStatus, PropertyType
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.services.auth_service import AuthService


class TestComprehensiveRoleAwareScenarios:
    """Comprehensive tests for all role-aware scenarios"""
    
    @pytest.fixture
    def test_user_seller(self, db_session, auth_service, test_roles):
        """Create test seller user"""
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
        
        return seller
    
    @pytest.fixture
    def seller_headers(self, client, test_user_seller):
        """Seller authentication headers"""
        login_response = client.post("/api/auth/login", data={
            "username": "seller@test.com",
            "password": "sellerpass"
        })
        token = login_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    @pytest.fixture
    def test_user_tenant(self, db_session, auth_service, test_roles):
        """Create test tenant user"""
        hashed_password = auth_service.get_password_hash("tenantpass")
        tenant = User(
            email="tenant@test.com",
            username="tenant_user",
            first_name="Test",
            last_name="Tenant",
            hashed_password=hashed_password
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)
        
        tenant_role = db_session.query(Role).filter(Role.name == "tenant").first()
        user_role = UserRole(user_id=tenant.id, role_id=tenant_role.id)
        db_session.add(user_role)
        db_session.commit()
        
        return tenant
    
    @pytest.fixture
    def tenant_headers(self, client, test_user_tenant):
        """Tenant authentication headers"""
        login_response = client.post("/api/auth/login", data={
            "username": "tenant@test.com",
            "password": "tenantpass"
        })
        token = login_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    
    @pytest.fixture
    def test_properties_setup(self, db_session, test_user_seller, test_user_admin):
        """Create comprehensive test properties for all scenarios"""
        properties = []
        
        # Public ACTIVE listings (should be visible to all)
        properties.append(Property(
            title="Public Active For Sale",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.ACTIVE,
            listing_type=ListingType.FOR_SALE,
            is_active=True,
            address="123 Public St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            price=100000,
            owner_id=999  # Different owner
        ))
        
        properties.append(Property(
            title="Public Active For Rent",
            description="Test",
            property_type=PropertyType.APARTMENT,
            status=PropertyStatus.ACTIVE,
            listing_type=ListingType.FOR_RENT,
            is_active=True,
            address="456 Public St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            price=2000,
            owner_id=888  # Different owner
        ))
        
        # Seller's own properties (various statuses)
        properties.append(Property(
            title="Seller's Draft Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.DRAFT,
            listing_type=ListingType.FOR_SALE,
            is_active=True,
            address="789 Seller St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            price=300000,
            owner_id=test_user_seller.id  # Seller's own
        ))
        
        properties.append(Property(
            title="Seller's Active Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.ACTIVE,
            listing_type=ListingType.FOR_SALE,
            is_active=True,
            address="101 Seller St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            price=400000,
            owner_id=test_user_seller.id  # Seller's own
        ))
        
        properties.append(Property(
            title="Seller's Sold Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.SOLD,
            listing_type=ListingType.FOR_SALE,
            is_active=True,
            address="202 Seller St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            price=500000,
            owner_id=test_user_seller.id  # Seller's own
        ))
        
        # DELETED property (should not be visible except to admin on /all)
        properties.append(Property(
            title="Deleted Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.DELETED,
            listing_type=ListingType.FOR_SALE,
            is_active=False,
            address="303 Deleted St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            price=600000,
            owner_id=test_user_seller.id
        ))
        
        # FOR_PORTFOLIO property (should not be visible to public/buyer/tenant)
        properties.append(Property(
            title="Portfolio Property",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.ACTIVE,
            listing_type=ListingType.FOR_PORTFOLIO,
            is_active=True,
            address="404 Portfolio St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            price=700000,
            owner_id=777  # Different owner
        ))
        
        # Another owner's DRAFT (should not be visible to seller)
        properties.append(Property(
            title="Other Owner's Draft",
            description="Test",
            property_type=PropertyType.HOUSE,
            status=PropertyStatus.DRAFT,
            listing_type=ListingType.FOR_SALE,
            is_active=True,
            address="505 Other St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            price=800000,
            owner_id=666  # Different owner
        ))
        
        for prop in properties:
            db_session.add(prop)
        db_session.commit()
        
        return properties
    
    # ==================== GET /api/properties/ Tests ====================
    
    def test_public_user_sees_only_active_public_listings(
        self, client, db_session, test_roles, test_properties_setup
    ):
        """Public/Guest: Only ACTIVE + public listings"""
        response = client.get("/api/properties/")
        assert response.status_code == 200
        data = response.json()
        
        # Should see 3 ACTIVE public listings (including seller's active property)
        assert data["total_count"] == 3
        property_titles = [p["title"] for p in data["properties"]]
        assert "Public Active For Sale" in property_titles
        assert "Public Active For Rent" in property_titles
        assert "Seller's Active Property" in property_titles  # ACTIVE + FOR_SALE = visible to public
        
        # Should NOT see:
        # - Draft properties
        # - Portfolio properties
        # - Deleted properties
        # - Other owner's non-ACTIVE properties
        assert "Seller's Draft Property" not in property_titles
        assert "Seller's Sold Property" not in property_titles
        assert "Portfolio Property" not in property_titles
        assert "Deleted Property" not in property_titles
        assert "Other Owner's Draft" not in property_titles
        
        # Verify all returned properties are ACTIVE and public listing types
        for prop in data["properties"]:
            assert prop["status"] == "active"
            assert prop["listing_type"] in ["for_sale", "for_rent", "for_lease"]
            assert prop["is_active"] is True
    
    def test_buyer_sees_only_active_public_listings(
        self, client, buyer_headers, db_session, test_roles, test_properties_setup
    ):
        """Buyer/Tenant: Same as public"""
        response = client.get("/api/properties/", headers=buyer_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should see 3 ACTIVE public listings (same as public)
        assert data["total_count"] == 3
        property_titles = [p["title"] for p in data["properties"]]
        assert "Public Active For Sale" in property_titles
        assert "Public Active For Rent" in property_titles
        assert "Seller's Active Property" in property_titles  # ACTIVE + FOR_SALE = visible
        
        # Should NOT see portfolio or deleted
        assert "Portfolio Property" not in property_titles
        assert "Deleted Property" not in property_titles
        assert "Seller's Draft Property" not in property_titles
        assert "Seller's Sold Property" not in property_titles
    
    def test_tenant_sees_only_active_public_listings(
        self, client, tenant_headers, db_session, test_roles, test_properties_setup
    ):
        """Tenant: Same as public"""
        response = client.get("/api/properties/", headers=tenant_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should see 3 ACTIVE public listings (same as public)
        assert data["total_count"] == 3
        property_titles = [p["title"] for p in data["properties"]]
        assert "Public Active For Sale" in property_titles
        assert "Public Active For Rent" in property_titles
        assert "Seller's Active Property" in property_titles  # ACTIVE + FOR_SALE = visible
        
        # Should NOT see portfolio or deleted
        assert "Portfolio Property" not in property_titles
        assert "Deleted Property" not in property_titles
        assert "Seller's Draft Property" not in property_titles
        assert "Seller's Sold Property" not in property_titles
    
    def test_seller_sees_active_and_own_properties(
        self, client, seller_headers, db_session, test_roles, test_properties_setup, test_user_seller
    ):
        """Seller: All own listings (any status except DELETED) + public ACTIVE"""
        response = client.get("/api/properties/", headers=seller_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should see:
        # - 2 public ACTIVE listings (from other owners)
        # - 3 own properties (DRAFT, ACTIVE, SOLD) - but NOT DELETED
        # Note: Seller's Active Property is counted in both public and own, but query deduplicates
        # Total: 5 properties (2 public + 3 own, but seller's active is public so it's included)
        assert data["total_count"] == 5
        property_titles = [p["title"] for p in data["properties"]]
        
        # Public listings
        assert "Public Active For Sale" in property_titles
        assert "Public Active For Rent" in property_titles
        
        # Own properties (except deleted)
        assert "Seller's Draft Property" in property_titles
        assert "Seller's Active Property" in property_titles
        assert "Seller's Sold Property" in property_titles
        
        # Should NOT see:
        assert "Deleted Property" not in property_titles  # Own but deleted
        assert "Other Owner's Draft" not in property_titles  # Not own
        assert "Portfolio Property" not in property_titles  # Not own and not public
    
    def test_admin_sees_all_non_deleted_properties(
        self, client, admin_headers, db_session, test_roles, test_properties_setup
    ):
        """Admin: All non-DELETED listings"""
        response = client.get("/api/properties/", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should see all properties except DELETED
        # Total: 7 properties (all except deleted)
        assert data["total_count"] == 7
        property_titles = [p["title"] for p in data["properties"]]
        
        # Should see all statuses except deleted
        assert "Public Active For Sale" in property_titles
        assert "Public Active For Rent" in property_titles
        assert "Seller's Draft Property" in property_titles
        assert "Seller's Active Property" in property_titles
        assert "Seller's Sold Property" in property_titles
        assert "Portfolio Property" in property_titles
        assert "Other Owner's Draft" in property_titles
        
        # Should NOT see deleted
        assert "Deleted Property" not in property_titles
    
    def test_admin_all_endpoint_sees_deleted(
        self, client, admin_headers, db_session, test_roles, test_properties_setup
    ):
        """Admin /all endpoint: All listings including DELETED"""
        response = client.get("/api/properties/all", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should see ALL properties including DELETED
        # Total: 8 properties (including deleted)
        assert data["total_count"] == 8
        property_titles = [p["title"] for p in data["properties"]]
        
        # Should see deleted property
        assert "Deleted Property" in property_titles
        
        # Should see all other properties too
        assert "Public Active For Sale" in property_titles
        assert "Public Active For Rent" in property_titles
        assert "Seller's Draft Property" in property_titles
        assert "Seller's Active Property" in property_titles
        assert "Seller's Sold Property" in property_titles
        assert "Portfolio Property" in property_titles
        assert "Other Owner's Draft" in property_titles
    
    # ==================== GET /api/properties/{id} Tests ====================
    
    def test_owner_can_view_own_property_any_status(
        self, client, seller_headers, db_session, test_roles, test_properties_setup, test_user_seller
    ):
        """Owner: Own properties visible regardless of status"""
        # Get seller's draft property ID
        draft_prop = db_session.query(Property).filter(
            Property.title == "Seller's Draft Property"
        ).first()
        
        response = client.get(f"/api/properties/{draft_prop.id}", headers=seller_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Seller's Draft Property"
        assert data["status"] == "draft"
        
        # Get seller's sold property ID
        sold_prop = db_session.query(Property).filter(
            Property.title == "Seller's Sold Property"
        ).first()
        
        response = client.get(f"/api/properties/{sold_prop.id}", headers=seller_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Seller's Sold Property"
        assert data["status"] == "sold"
        
        # Should NOT be able to see own deleted property
        deleted_prop = db_session.query(Property).filter(
            Property.title == "Deleted Property"
        ).first()
        
        response = client.get(f"/api/properties/{deleted_prop.id}", headers=seller_headers)
        assert response.status_code == 403  # Permission denied
    
    def test_owner_cannot_view_other_owner_draft(
        self, client, seller_headers, db_session, test_roles, test_properties_setup
    ):
        """Owner: Cannot view other owner's non-ACTIVE properties"""
        other_draft = db_session.query(Property).filter(
            Property.title == "Other Owner's Draft"
        ).first()
        
        response = client.get(f"/api/properties/{other_draft.id}", headers=seller_headers)
        assert response.status_code == 403  # Permission denied
    
    def test_owner_can_view_public_active_properties(
        self, client, seller_headers, db_session, test_roles, test_properties_setup
    ):
        """Owner: Can view public ACTIVE properties"""
        public_prop = db_session.query(Property).filter(
            Property.title == "Public Active For Sale"
        ).first()
        
        response = client.get(f"/api/properties/{public_prop.id}", headers=seller_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Public Active For Sale"
    
    def test_non_owner_can_only_view_active_public(
        self, client, buyer_headers, db_session, test_roles, test_properties_setup
    ):
        """Non-owner: Only ACTIVE + public"""
        # Can view public ACTIVE
        public_prop = db_session.query(Property).filter(
            Property.title == "Public Active For Sale"
        ).first()
        
        response = client.get(f"/api/properties/{public_prop.id}", headers=buyer_headers)
        assert response.status_code == 200
        
        # Cannot view draft
        draft_prop = db_session.query(Property).filter(
            Property.title == "Seller's Draft Property"
        ).first()
        
        response = client.get(f"/api/properties/{draft_prop.id}", headers=buyer_headers)
        assert response.status_code == 403
        
        # Cannot view portfolio
        portfolio_prop = db_session.query(Property).filter(
            Property.title == "Portfolio Property"
        ).first()
        
        response = client.get(f"/api/properties/{portfolio_prop.id}", headers=buyer_headers)
        assert response.status_code == 403
        
        # Cannot view deleted
        deleted_prop = db_session.query(Property).filter(
            Property.title == "Deleted Property"
        ).first()
        
        response = client.get(f"/api/properties/{deleted_prop.id}", headers=buyer_headers)
        assert response.status_code == 403
    
    def test_public_can_only_view_active_public(
        self, client, db_session, test_roles, test_properties_setup
    ):
        """Public: Only ACTIVE + public"""
        # Can view public ACTIVE
        public_prop = db_session.query(Property).filter(
            Property.title == "Public Active For Sale"
        ).first()
        
        response = client.get(f"/api/properties/{public_prop.id}")
        assert response.status_code == 200
        
        # Cannot view draft
        draft_prop = db_session.query(Property).filter(
            Property.title == "Seller's Draft Property"
        ).first()
        
        response = client.get(f"/api/properties/{draft_prop.id}")
        assert response.status_code == 403
        
        # Cannot view portfolio
        portfolio_prop = db_session.query(Property).filter(
            Property.title == "Portfolio Property"
        ).first()
        
        response = client.get(f"/api/properties/{portfolio_prop.id}")
        assert response.status_code == 403
    
    def test_admin_can_view_all_properties(
        self, client, admin_headers, db_session, test_roles, test_properties_setup
    ):
        """Admin: Can view all properties including deleted"""
        # Can view active
        active_prop = db_session.query(Property).filter(
            Property.title == "Public Active For Sale"
        ).first()
        
        response = client.get(f"/api/properties/{active_prop.id}", headers=admin_headers)
        assert response.status_code == 200
        
        # Can view draft
        draft_prop = db_session.query(Property).filter(
            Property.title == "Seller's Draft Property"
        ).first()
        
        response = client.get(f"/api/properties/{draft_prop.id}", headers=admin_headers)
        assert response.status_code == 200
        
        # Can view deleted
        deleted_prop = db_session.query(Property).filter(
            Property.title == "Deleted Property"
        ).first()
        
        response = client.get(f"/api/properties/{deleted_prop.id}", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        
        # Can view portfolio
        portfolio_prop = db_session.query(Property).filter(
            Property.title == "Portfolio Property"
        ).first()
        
        response = client.get(f"/api/properties/{portfolio_prop.id}", headers=admin_headers)
        assert response.status_code == 200

