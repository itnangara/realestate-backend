"""
Enterprise-grade tests for lease validation and dual-origin creation
Simple, production-ready tests
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi.testclient import TestClient

from app.schemas.lease import LeaseCreate
from app.models.lease import LeaseStatus


class TestLeaseSchemaValidation:
    """Test schema validation for dual-origin lease creation"""
    
    def test_manual_lease_requires_both_property_and_tenant(self):
        """Test that manual lease requires both property_id and tenant_id"""
        # Missing property_id
        with pytest.raises(ValueError, match="property_id.*tenant_id.*required"):
            LeaseCreate(
                tenant_id=1,
                rent=Decimal("1500.00"),
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc) + timedelta(days=365)
            )
        
        # Missing tenant_id
        with pytest.raises(ValueError, match="property_id.*tenant_id.*required"):
            LeaseCreate(
                property_id=1,
                rent=Decimal("1500.00"),
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc) + timedelta(days=365)
            )
    
    def test_application_driven_rejects_property_id(self):
        """Test that application-driven lease rejects property_id"""
        with pytest.raises(ValueError, match="Cannot provide property_id"):
            LeaseCreate(
                application_id=1,
                property_id=1,  # Should not be provided
                rent=Decimal("1500.00"),
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc) + timedelta(days=365)
            )
    
    def test_application_driven_rejects_tenant_id(self):
        """Test that application-driven lease rejects tenant_id"""
        with pytest.raises(ValueError, match="Cannot provide.*tenant_id"):
            LeaseCreate(
                application_id=1,
                tenant_id=1,  # Should not be provided
                rent=Decimal("1500.00"),
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc) + timedelta(days=365)
            )
    
    def test_manual_lease_valid(self):
        """Test valid manual lease creation"""
        lease = LeaseCreate(
            property_id=1,
            tenant_id=1,
            rent=Decimal("1500.00"),
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=365)
        )
        assert lease.property_id == 1
        assert lease.tenant_id == 1
        assert lease.application_id is None
    
    def test_application_driven_valid(self):
        """Test valid application-driven lease creation"""
        lease = LeaseCreate(
            application_id=1,
            rent=Decimal("1500.00"),
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=365)
        )
        assert lease.application_id == 1
        assert lease.property_id is None
        assert lease.tenant_id is None

