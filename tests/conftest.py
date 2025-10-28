"""
Test configuration and shared fixtures
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from app.utils.database import get_db, Base
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.services.auth_service import AuthService

# Use PostgreSQL in CI, SQLite locally for speed
import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///:memory:")

if DATABASE_URL.startswith("postgresql"):
    # PostgreSQL configuration for CI
    engine = create_engine(DATABASE_URL)
else:
    # SQLite configuration for local testing
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Override the database dependency
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def client():
    """Test client fixture"""
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Create test client with proper base URL to bypass middleware
    test_client = TestClient(app, base_url="http://localhost")
    yield test_client
    # Clean up
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Database session fixture"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def auth_service(db_session):
    """Auth service fixture"""
    return AuthService(db_session)


@pytest.fixture(scope="function")
def test_roles(db_session):
    """Create test roles"""
    roles_data = [
        ("buyer", "Can browse and apply for properties"),
        ("seller", "Can list properties for sale"),
        ("agent", "Real estate professional"),
        ("landlord", "Can rent out properties"),
        ("tenant", "Can rent properties"),
        ("investor", "Can invest in properties"),
        ("admin", "System administrator")
    ]
    
    roles = []
    for name, description in roles_data:
        role = Role(name=name, description=description)
        db_session.add(role)
        roles.append(role)
    
    db_session.commit()
    return roles


@pytest.fixture(scope="function")
def test_user_buyer(db_session, auth_service, test_roles):
    """Create test buyer user"""
    # Create user
    hashed_password = auth_service.get_password_hash("testpassword")
    user = User(
        email="buyer@test.com",
        username="buyer_user",
        first_name="Test",
        last_name="Buyer",
        hashed_password=hashed_password
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Assign buyer role
    buyer_role = db_session.query(Role).filter(Role.name == "buyer").first()
    user_role = UserRole(user_id=user.id, role_id=buyer_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


@pytest.fixture(scope="function")
def test_user_admin(db_session, auth_service, test_roles):
    """Create test admin user"""
    # Create user
    hashed_password = auth_service.get_password_hash("adminpassword")
    user = User(
        email="admin@test.com",
        username="admin_user",
        first_name="Test",
        last_name="Admin",
        hashed_password=hashed_password
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Assign admin role
    admin_role = db_session.query(Role).filter(Role.name == "admin").first()
    user_role = UserRole(user_id=user.id, role_id=admin_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


@pytest.fixture(scope="function")
def test_user_agent(db_session, auth_service, test_roles):
    """Create test agent user"""
    # Create user
    hashed_password = auth_service.get_password_hash("agentpassword")
    user = User(
        email="agent@test.com",
        username="agent_user",
        first_name="Test",
        last_name="Agent",
        hashed_password=hashed_password
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Assign agent role
    agent_role = db_session.query(Role).filter(Role.name == "agent").first()
    user_role = UserRole(user_id=user.id, role_id=agent_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


@pytest.fixture(scope="function")
def buyer_token(client, test_user_buyer):
    """Get buyer authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "buyer@test.com",
        "password": "testpassword"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="function")
def admin_token(client, test_user_admin):
    """Get admin authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "admin@test.com",
        "password": "adminpassword"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="function")
def agent_token(client, test_user_agent):
    """Get agent authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "agent@test.com",
        "password": "agentpassword"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="function")
def buyer_headers(buyer_token):
    """Buyer authentication headers"""
    return {"Authorization": f"Bearer {buyer_token}"}


@pytest.fixture(scope="function")
def admin_headers(admin_token):
    """Admin authentication headers"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="function")
def agent_headers(agent_token):
    """Agent authentication headers"""
    return {"Authorization": f"Bearer {agent_token}"}


@pytest.fixture(scope="function")
def test_property(client, buyer_headers):
    """Create a test property for use in tests"""
    property_data = {
        "title": "Test Property",
        "description": "Property for testing",
        "property_type": "house",
        "status": "for_sale",
        "address": "123 Test Street",
        "city": "Test City",
        "state": "TS",
        "zip_code": "12345",
        "price": 400000
    }
    
    response = client.post("/api/properties", json=property_data, headers=buyer_headers)
    assert response.status_code == 201
    return response.json()
