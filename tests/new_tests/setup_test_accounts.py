"""
Setup test accounts for manual testing
Creates: land-1@gmail.com, ten-1@gmail.com, admin@gmail.com
Run: python setup_test_accounts.py
"""
from app.utils.database import SessionLocal
from app.models.role import Role
from app.models.user import User, UserStatus
from app.models.user_role import UserRole
from app.services.auth_service import AuthService
from app.core.logger import get_logger
import logging

# Suppress SQLAlchemy info logs
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

logger = get_logger(__name__)

# Test accounts to create
TEST_ACCOUNTS = [
    {
        "email": "land-1@gmail.com",
        "username": "land-1",
        "password": "Admin@123",
        "first_name": "Test",
        "last_name": "Landlord",
        "roles": ["landlord"]
    },
    {
        "email": "ten-1@gmail.com",
        "username": "ten-1",
        "password": "Admin@123",
        "first_name": "Test",
        "last_name": "Tenant",
        "roles": ["tenant"]
    },
    {
        "email": "admin@gmail.com",
        "username": "admin",
        "password": "Admin@123",
        "first_name": "Admin",
        "last_name": "User",
        "roles": ["admin"]
    }
]

def ensure_role_exists(db, role_name: str) -> Role:
    """Ensure a role exists, create if not"""
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        role = Role(name=role_name, description=f"{role_name} role")
        db.add(role)
        db.commit()
        db.refresh(role)
        logger.info(f"Created role: {role_name}")
    return role

def create_or_update_test_user(db, account_data: dict):
    """Create or update a test user with specified roles"""
    auth_service = AuthService(db)
    
    # Check if user exists
    existing_user = db.query(User).filter(
        (User.email == account_data["email"]) | (User.username == account_data["username"])
    ).first()
    
    if existing_user:
        # Update existing user
        hashed_password = auth_service.get_password_hash(account_data["password"])
        existing_user.hashed_password = hashed_password
        existing_user.is_verified = True
        existing_user.status = UserStatus.ACTIVE
        db.commit()
        db.refresh(existing_user)
        user = existing_user
        print(f"   [UPDATED] User: {account_data['email']}")
    else:
        # Create new user
        hashed_password = auth_service.get_password_hash(account_data["password"])
        user = User(
            email=account_data["email"],
            username=account_data["username"],
            hashed_password=hashed_password,
            first_name=account_data["first_name"],
            last_name=account_data["last_name"],
            is_verified=True,
            status=UserStatus.ACTIVE
        )
        db.add(user)
        db.flush()
        print(f"   [CREATED] User: {account_data['email']}")
    
    # Ensure roles exist and assign them
    for role_name in account_data["roles"]:
        role = ensure_role_exists(db, role_name)
        
        # Check if user already has this role
        existing_user_role = db.query(UserRole).filter(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id
        ).first()
        
        if not existing_user_role:
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db.add(user_role)
            print(f"   [ASSIGNED] Role: {role_name}")
    
    db.commit()
    return user

def main():
    """Main function to set up test accounts"""
    print("=" * 60)
    print("SETTING UP TEST ACCOUNTS")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # First, ensure all required roles exist
        print("\n1. Ensuring required roles exist...")
        required_roles = ["landlord", "tenant", "admin", "buyer", "seller", "agent", "investor", "maintenance_staff"]
        for role_name in required_roles:
            ensure_role_exists(db, role_name)
        print(f"   [OK] All required roles exist")
        
        # Create test accounts
        print("\n2. Creating/updating test accounts...")
        for account_data in TEST_ACCOUNTS:
            create_or_update_test_user(db, account_data)
        
        print("\n" + "=" * 60)
        print("[SUCCESS] Test accounts setup complete!")
        print("=" * 60)
        print("\nTest Account Credentials:")
        print("-" * 60)
        for account in TEST_ACCOUNTS:
            print(f"Email: {account['email']}")
            print(f"Password: {account['password']}")
            print(f"Roles: {', '.join(account['roles'])}")
            print()
        
    except Exception as e:
        logger.error("setup_failed", error=str(e), exc_info=True)
        db.rollback()
        print(f"\n[ERROR] Setup failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()

