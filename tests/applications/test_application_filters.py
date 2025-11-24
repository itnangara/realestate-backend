"""
Enterprise-grade tests for application filtering and pagination

Following RCA Framework principles:
- Test exact status match (not partial)
- Test search functionality (numeric, exact)
- Test all filter combinations
- Verify pagination works correctly
- Test tenant vs landlord endpoint differences
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.models.application import Application, ApplicationStatus
from app.models.user import User
from app.models.property import Property, PropertyStatus, PropertyType, ListingType
from app.services.application_service import ApplicationService


@pytest.fixture(scope="function")
def test_users(db_session, auth_service, test_roles):
    """Create test users"""
    users = []
    for i in range(5):
        hashed_password = auth_service.get_password_hash(f"pass{i}")
        user = User(
            email=f"user{i}@test.com",
            username=f"user{i}",
            hashed_password=hashed_password,
            first_name=f"User{i}",
            last_name="Test",
            is_verified=True
        )
        db_session.add(user)
        users.append(user)
    db_session.commit()
    for user in users:
        db_session.refresh(user)
    return users


@pytest.fixture(scope="function", autouse=True)
def setup_application_tables(db_session):
    """Create tables needed for application filter tests"""
    from app.models.application import Application
    from app.models.property import Property
    from app.models.user import User
    
    # Create tables
    User.__table__.create(bind=db_session.bind, checkfirst=True)
    Property.__table__.create(bind=db_session.bind, checkfirst=True)
    Application.__table__.create(bind=db_session.bind, checkfirst=True)
    
    yield
    
    # Clean up
    try:
        Application.__table__.drop(bind=db_session.bind, checkfirst=True)
        Property.__table__.drop(bind=db_session.bind, checkfirst=True)
        User.__table__.drop(bind=db_session.bind, checkfirst=True)
    except Exception:
        pass


@pytest.fixture(scope="function")
def test_properties(db_session, test_users):
    """Create test properties"""
    properties = []
    landlord = test_users[0]  # User 0 is landlord
    
    for i in range(3):
        prop = Property(
            title=f"Property {i+1}",
            property_type=PropertyType.HOUSE,
            listing_type=ListingType.FOR_RENT,
            status=PropertyStatus.ACTIVE,
            address=f"{i+1} Main St",
            city="Test City",
            state="TS",
            zip_code="12345",
            country="USA",
            price=1000 * (i + 1),
            owner_id=landlord.id,
            is_active=True
        )
        db_session.add(prop)
        properties.append(prop)
    db_session.commit()
    for prop in properties:
        db_session.refresh(prop)
    return properties


@pytest.fixture(scope="function")
def test_applications(db_session, test_users, test_properties):
    """Create test applications with various statuses and dates"""
    applications = []
    landlord = test_users[0]
    tenant1 = test_users[1]
    tenant2 = test_users[2]
    base_date = datetime.now(timezone.utc)
    
    # Tenant 1 applications
    applications.append(Application(
        applicant_id=tenant1.id,
        property_id=test_properties[0].id,
        status=ApplicationStatus.DRAFT,
        created_at=base_date - timedelta(days=5)
    ))
    applications.append(Application(
        applicant_id=tenant1.id,
        property_id=test_properties[1].id,
        status=ApplicationStatus.APPROVED,
        created_at=base_date - timedelta(days=4)
    ))
    
    # Tenant 2 applications
    applications.append(Application(
        applicant_id=tenant2.id,
        property_id=test_properties[0].id,
        status=ApplicationStatus.SUBMITTED,
        created_at=base_date - timedelta(days=3)
    ))
    applications.append(Application(
        applicant_id=tenant2.id,
        property_id=test_properties[2].id,
        status=ApplicationStatus.REJECTED,
        created_at=base_date - timedelta(days=2)
    ))
    
    # Tenant 1 - another application
    applications.append(Application(
        applicant_id=tenant1.id,
        property_id=test_properties[2].id,
        status=ApplicationStatus.REVIEWED,
        created_at=base_date - timedelta(days=1)
    ))
    
    for app in applications:
        db_session.add(app)
    db_session.commit()
    for app in applications:
        db_session.refresh(app)
    return applications


class TestStatusFilter:
    """Test status filter - EXACT MATCH"""
    
    def test_status_filter_exact_match_tenant(self, db_session, test_applications, test_users):
        """Test tenant endpoint status filter - exact match"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            status=ApplicationStatus.APPROVED
        )
        
        assert total == 1
        assert len(items) == 1
        assert items[0].status == ApplicationStatus.APPROVED
        assert items[0].applicant_id == tenant.id
    
    def test_status_filter_draft_exact_match(self, db_session, test_applications, test_users):
        """Test status filter returns ONLY draft applications"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            status=ApplicationStatus.DRAFT
        )
        
        assert total == 1
        assert len(items) == 1
        assert items[0].status == ApplicationStatus.DRAFT
    
    def test_status_filter_exact_match_landlord(self, db_session, test_applications, test_users):
        """Test landlord endpoint status filter - exact match"""
        service = ApplicationService(db_session)
        landlord = test_users[0]
        
        items, total = service.get_filtered_applications(
            landlord_id=landlord.id,
            status=ApplicationStatus.SUBMITTED
        )
        
        assert total == 1
        assert len(items) == 1
        assert items[0].status == ApplicationStatus.SUBMITTED
    
    def test_status_filter_none_returns_all(self, db_session, test_applications, test_users):
        """Test no status filter returns all applications"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id
        )
        
        # Tenant 1 has 3 applications
        assert total == 3
        assert len(items) == 3


class TestSearchFilter:
    """Test search filter - numeric, exact match"""
    
    def test_search_by_application_id_tenant(self, db_session, test_applications, test_users):
        """Test tenant search by application ID"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        target_app = test_applications[0]
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            search=str(target_app.id)
        )
        
        assert total == 1
        assert items[0].id == target_app.id
    
    def test_search_by_property_id_tenant(self, db_session, test_applications, test_users, test_properties):
        """Test tenant search by property ID"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        target_property = test_properties[0]
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            search=str(target_property.id)
        )
        
        # Tenant 1 has 2 applications for property 0
        assert total == 2
        assert all(app.property_id == target_property.id for app in items)
    
    def test_search_by_application_id_landlord(self, db_session, test_applications, test_users):
        """Test landlord search by application ID"""
        service = ApplicationService(db_session)
        landlord = test_users[0]
        target_app = test_applications[2]
        
        items, total = service.get_filtered_applications(
            landlord_id=landlord.id,
            search=str(target_app.id)
        )
        
        assert total == 1
        assert items[0].id == target_app.id
    
    def test_search_by_applicant_id_landlord(self, db_session, test_applications, test_users):
        """Test landlord search by applicant ID"""
        service = ApplicationService(db_session)
        landlord = test_users[0]
        tenant = test_users[1]
        
        items, total = service.get_filtered_applications(
            landlord_id=landlord.id,
            search=str(tenant.id)
        )
        
        # Tenant 1 has 3 applications for landlord's properties
        assert total == 3
        assert all(app.applicant_id == tenant.id for app in items)
    
    def test_search_invalid_ignored(self, db_session, test_applications, test_users):
        """Test invalid search is gracefully ignored"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            search="invalid"
        )
        
        # Should return all tenant's applications (search ignored)
        assert total == 3  # Tenant 1 has 3 applications


class TestPropertyIdFilter:
    """Test property_id filter"""
    
    def test_property_id_filter_tenant(self, db_session, test_applications, test_users, test_properties):
        """Test tenant property_id filter"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        target_property = test_properties[0]
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            property_id=target_property.id
        )
        
        assert total == 2
        assert all(app.property_id == target_property.id for app in items)
    
    def test_property_id_filter_landlord(self, db_session, test_applications, test_users, test_properties):
        """Test landlord property_id filter"""
        service = ApplicationService(db_session)
        landlord = test_users[0]
        target_property = test_properties[0]
        
        items, total = service.get_filtered_applications(
            landlord_id=landlord.id,
            property_id=target_property.id
        )
        
        assert total == 2
        assert all(app.property_id == target_property.id for app in items)


class TestApplicantIdFilter:
    """Test applicant_id filter (landlord-only)"""
    
    def test_applicant_id_filter_landlord(self, db_session, test_applications, test_users):
        """Test landlord applicant_id filter"""
        service = ApplicationService(db_session)
        landlord = test_users[0]
        tenant = test_users[1]
        
        items, total = service.get_filtered_applications(
            landlord_id=landlord.id,
            applicant_id=tenant.id
        )
        
        assert total == 3
        assert all(app.applicant_id == tenant.id for app in items)


class TestDateRangeFilter:
    """Test date range filters"""
    
    def test_date_from_filter(self, db_session, test_applications, test_users):
        """Test date_from filter"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        date_from = datetime.now(timezone.utc) - timedelta(days=2)
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            date_from=date_from
        )
        
        assert total >= 1
        for app in items:
            app_date = app.created_at
            if app_date.tzinfo is None:
                app_date = app_date.replace(tzinfo=timezone.utc)
            assert app_date >= date_from
    
    def test_date_to_filter(self, db_session, test_applications, test_users):
        """Test date_to filter"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        date_to = datetime.now(timezone.utc) - timedelta(days=3)
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            date_to=date_to
        )
        
        assert total >= 1
        for app in items:
            app_date = app.created_at
            if app_date.tzinfo is None:
                app_date = app_date.replace(tzinfo=timezone.utc)
            assert app_date <= date_to
    
    def test_date_range_filter(self, db_session, test_applications, test_users):
        """Test date range filter"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        date_from = datetime.now(timezone.utc) - timedelta(days=4)
        date_to = datetime.now(timezone.utc) - timedelta(days=2)
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            date_from=date_from,
            date_to=date_to
        )
        
        assert total >= 1
        for app in items:
            app_date = app.created_at
            if app_date.tzinfo is None:
                app_date = app_date.replace(tzinfo=timezone.utc)
            assert date_from <= app_date <= date_to


class TestCombinedFilters:
    """Test filter combinations (AND logic)"""
    
    def test_status_and_property_filter(self, db_session, test_applications, test_users, test_properties):
        """Test status + property_id combination"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            status=ApplicationStatus.APPROVED,
            property_id=test_properties[1].id
        )
        
        assert total == 1
        assert items[0].status == ApplicationStatus.APPROVED
        assert items[0].property_id == test_properties[1].id
    
    def test_all_filters_combined_tenant(self, db_session, test_applications, test_users, test_properties):
        """Test all filters combined for tenant"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        date_from = datetime.now(timezone.utc) - timedelta(days=10)
        date_to = datetime.now(timezone.utc)
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            status=ApplicationStatus.DRAFT,
            property_id=test_properties[0].id,
            date_from=date_from,
            date_to=date_to,
            search=str(test_applications[0].id),
            page=1,
            limit=10
        )
        
        assert total == 1
        assert items[0].id == test_applications[0].id
    
    def test_all_filters_combined_landlord(self, db_session, test_applications, test_users, test_properties):
        """Test all filters combined for landlord"""
        service = ApplicationService(db_session)
        landlord = test_users[0]
        tenant = test_users[1]
        
        items, total = service.get_filtered_applications(
            landlord_id=landlord.id,
            status=ApplicationStatus.APPROVED,
            property_id=test_properties[1].id,
            applicant_id=tenant.id,
            search=str(test_applications[1].id),
            page=1,
            limit=10
        )
        
        assert total == 1
        assert items[0].id == test_applications[1].id


class TestPagination:
    """Test pagination"""
    
    def test_pagination_limit(self, db_session, test_applications, test_users):
        """Test pagination with limit"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            page=1,
            limit=2
        )
        
        assert len(items) == 2
        assert total == 3  # Tenant 1 has 3 applications
    
    def test_pagination_offset(self, db_session, test_applications, test_users):
        """Test pagination with offset"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        
        page1, total1 = service.get_filtered_applications(
            user_id=tenant.id,
            page=1,
            limit=2
        )
        page2, total2 = service.get_filtered_applications(
            user_id=tenant.id,
            page=2,
            limit=2
        )
        
        assert len(page1) == 2
        assert len(page2) == 1
        assert total1 == total2 == 3
        assert page1[0].id != page2[0].id
    
    def test_pagination_with_filters(self, db_session, test_applications, test_users):
        """Test pagination with status filter"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            status=ApplicationStatus.APPROVED,
            page=1,
            limit=1
        )
        
        assert len(items) == 1
        assert total == 1
        assert items[0].status == ApplicationStatus.APPROVED


class TestTenantVsLandlordDifferences:
    """Test differences between tenant and landlord endpoints"""
    
    def test_tenant_only_sees_own_applications(self, db_session, test_applications, test_users):
        """Test tenant endpoint only returns own applications"""
        service = ApplicationService(db_session)
        tenant1 = test_users[1]
        tenant2 = test_users[2]
        
        items1, total1 = service.get_filtered_applications(user_id=tenant1.id)
        items2, total2 = service.get_filtered_applications(user_id=tenant2.id)
        
        # Tenant 1 has 3 applications, Tenant 2 has 2
        assert total1 == 3
        assert total2 == 2
        assert all(app.applicant_id == tenant1.id for app in items1)
        assert all(app.applicant_id == tenant2.id for app in items2)
    
    def test_landlord_only_sees_own_properties(self, db_session, test_applications, test_users):
        """Test landlord endpoint only returns applications for own properties"""
        service = ApplicationService(db_session)
        landlord = test_users[0]
        
        items, total = service.get_filtered_applications(landlord_id=landlord.id)
        
        # All applications are for landlord's properties
        assert total == 5
        property_ids = {app.property_id for app in items}
        # Verify all properties belong to landlord
        landlord_properties = db_session.query(Property).filter(
            Property.owner_id == landlord.id
        ).all()
        landlord_property_ids = {p.id for p in landlord_properties}
        assert property_ids.issubset(landlord_property_ids)
    
    def test_landlord_search_includes_applicant_id(self, db_session, test_applications, test_users):
        """Test landlord search includes applicant_id, tenant search does not"""
        service = ApplicationService(db_session)
        landlord = test_users[0]
        tenant = test_users[1]
        
        # Landlord search by applicant_id should work
        items, total = service.get_filtered_applications(
            landlord_id=landlord.id,
            search=str(tenant.id)
        )
        
        assert total == 3
        assert all(app.applicant_id == tenant.id for app in items)
    
    def test_tenant_search_excludes_applicant_id(self, db_session, test_applications, test_users):
        """Test tenant search does not include applicant_id"""
        service = ApplicationService(db_session)
        tenant = test_users[1]
        other_tenant = test_users[2]
        
        # Tenant search by other tenant's ID should not work
        items, total = service.get_filtered_applications(
            user_id=tenant.id,
            search=str(other_tenant.id)
        )
        
        # Should return 0 (search doesn't match application_id or property_id)
        assert total == 0

