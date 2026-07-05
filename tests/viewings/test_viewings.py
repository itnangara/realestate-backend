"""
Tests for property viewing requests.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.property import ListingType, Property, PropertyStatus, PropertyType
from app.models.role import Role
from app.models.user import User
from app.models.user_property import RelationshipType, UserProperty
from app.models.user_role import UserRole


def _ensure_role(db_session, name: str) -> Role:
    role = db_session.query(Role).filter(Role.name == name).first()
    if role:
        return role
    role = Role(name=name, description=f"{name} role")
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


def _create_user(db_session, auth_service, role_name: str, email: str, password: str) -> User:
    role = _ensure_role(db_session, role_name)
    user = User(
        email=email,
        username=email.split("@")[0],
        first_name=role_name.title(),
        last_name="User",
        hashed_password=auth_service.get_password_hash(password),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client, email: str, password: str) -> dict:
    response = client.post("/api/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def viewing_setup(client, db_session, auth_service):
    landlord = _create_user(db_session, auth_service, "landlord", "viewing-landlord@test.com", "password")
    tenant = _create_user(db_session, auth_service, "tenant", "viewing-tenant@test.com", "password")
    buyer = _create_user(db_session, auth_service, "buyer", "viewing-buyer@test.com", "password")

    property_obj = Property(
        title="Berlin Rental",
        description="Two bedroom flat",
        property_type=PropertyType.APARTMENT,
        listing_type=ListingType.FOR_RENT,
        status=PropertyStatus.ACTIVE,
        address="1 Test Strasse",
        city="Berlin",
        state="Berlin",
        zip_code="10115",
        country="Germany",
        rent_price=1450,
        is_active=True,
    )
    db_session.add(property_obj)
    db_session.flush()

    db_session.add(
        UserProperty(
            user_id=landlord.id,
            property_id=property_obj.id,
            relationship_type=RelationshipType.LANDLORD,
        )
    )
    db_session.commit()
    db_session.refresh(property_obj)

    return {
        "property": property_obj,
        "landlord_headers": _login(client, "viewing-landlord@test.com", "password"),
        "tenant_headers": _login(client, "viewing-tenant@test.com", "password"),
        "buyer_headers": _login(client, "viewing-buyer@test.com", "password"),
        "landlord": landlord,
        "tenant": tenant,
        "buyer": buyer,
    }


def test_tenant_can_create_viewing_request(client, viewing_setup):
    slot = datetime.now(timezone.utc) + timedelta(days=2)

    response = client.post(
        "/api/viewings",
        json={
            "property_id": viewing_setup["property"].id,
            "requested_slots": [slot.isoformat()],
            "message": "Friday afternoon works best.",
        },
        headers=viewing_setup["tenant_headers"],
    )

    assert response.status_code == 201
    data = response.json()
    assert data["property_id"] == viewing_setup["property"].id
    assert data["status"] == "PENDING"
    assert data["assigned_to_id"] == viewing_setup["landlord"].id
    assert data["property"]["title"] == "Berlin Rental"


def test_property_manager_can_confirm_viewing_request(client, viewing_setup):
    slot = datetime.now(timezone.utc) + timedelta(days=3)
    create_response = client.post(
        "/api/viewings",
        json={
            "property_id": viewing_setup["property"].id,
            "requested_slots": [slot.isoformat()],
        },
        headers=viewing_setup["tenant_headers"],
    )
    viewing_id = create_response.json()["id"]

    confirm_response = client.post(
        f"/api/viewings/{viewing_id}/confirm",
        json={"confirmed_slot": slot.isoformat(), "response_note": "Confirmed, see you then."},
        headers=viewing_setup["landlord_headers"],
    )

    assert confirm_response.status_code == 200
    data = confirm_response.json()
    assert data["status"] == "CONFIRMED"
    assert data["confirmed_slot"] is not None


def test_non_manager_cannot_confirm_viewing_request(client, viewing_setup):
    slot = datetime.now(timezone.utc) + timedelta(days=4)
    create_response = client.post(
        "/api/viewings",
        json={
            "property_id": viewing_setup["property"].id,
            "requested_slots": [slot.isoformat()],
        },
        headers=viewing_setup["tenant_headers"],
    )
    viewing_id = create_response.json()["id"]

    confirm_response = client.post(
        f"/api/viewings/{viewing_id}/confirm",
        json={"confirmed_slot": slot.isoformat()},
        headers=viewing_setup["buyer_headers"],
    )

    assert confirm_response.status_code == 403


def test_requester_can_cancel_own_viewing_request(client, viewing_setup):
    slot = datetime.now(timezone.utc) + timedelta(days=5)
    create_response = client.post(
        "/api/viewings",
        json={
            "property_id": viewing_setup["property"].id,
            "requested_slots": [slot.isoformat()],
        },
        headers=viewing_setup["tenant_headers"],
    )
    viewing_id = create_response.json()["id"]

    cancel_response = client.post(
        f"/api/viewings/{viewing_id}/cancel",
        json={"reason": "Plans changed"},
        headers=viewing_setup["tenant_headers"],
    )

    assert cancel_response.status_code == 200
    data = cancel_response.json()
    assert data["status"] == "CANCELLED"
    assert data["cancellation_reason"] == "Plans changed"
