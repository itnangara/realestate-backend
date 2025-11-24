"""
Database seeding script - creates essential data for application to work
Run: python seed_database.py
"""
from app.utils.database import SessionLocal, engine, Base
from app.models.role import Role
from app.models.user import User, UserStatus
from app.models.user_role import UserRole
from app.services.auth_service import AuthService
from app.core.logger import get_logger
import logging

# Suppress SQLAlchemy info logs
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

logger = get_logger(__name__)

# Required roles for the application
REQUIRED_ROLES = [
    {"name": "buyer", "description": "User looking to buy properties"},
    {"name": "seller", "description": "User selling properties"},
    {"name": "agent", "description": "Real estate agent"},
    {"name": "landlord", "description": "Property owner renting properties"},
    {"name": "tenant", "description": "User looking to rent properties"},
    {"name": "investor", "description": "Property investor"},
    {"name": "admin", "description": "System administrator"}
]

def seed_roles(db):
    """Create all required roles if they don't exist"""
    created_count = 0
    existing_count = 0
    
    for role_data in REQUIRED_ROLES:
        existing_role = db.query(Role).filter(Role.name == role_data["name"]).first()
        if not existing_role:
            role = Role(**role_data)
            db.add(role)
            created_count += 1
            logger.info(f"Created role: {role_data['name']}")
        else:
            existing_count += 1
    
    if created_count > 0:
        db.commit()
        logger.info(f"Seeded {created_count} roles")
    
    if existing_count > 0:
        logger.info(f"{existing_count} roles already exist")
    
    return created_count, existing_count

def seed_admin_user(db):
    """Create a default admin user if it doesn't exist"""
    admin_email = "admin@realestate.com"
    admin_username = "admin"
    
    # Check if admin user exists by email or username
    existing_admin = db.query(User).filter(
        (User.email == admin_email) | (User.username == admin_username)
    ).first()
    
    if existing_admin:
        # Check if user has admin role, if not, assign it
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if admin_role:
            existing_role = db.query(UserRole).filter(
                UserRole.user_id == existing_admin.id,
                UserRole.role_id == admin_role.id
            ).first()
            
            if not existing_role:
                user_role = UserRole(user_id=existing_admin.id, role_id=admin_role.id)
                db.add(user_role)
                db.commit()
                logger.info(f"Assigned admin role to existing user: {existing_admin.email}")
            else:
                logger.info("Admin user already exists with admin role")
        return existing_admin
    
    # Get admin role
    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        logger.error("Admin role not found - run seed_roles first")
        return None
    
    # Create admin user
    auth_service = AuthService(db)
    hashed_password = auth_service.get_password_hash("admin123")
    
    admin_user = User(
        email=admin_email,
        username="admin",
        hashed_password=hashed_password,
        first_name="Admin",
        last_name="User",
        is_verified=True,
        status=UserStatus.ACTIVE
    )
    db.add(admin_user)
    db.flush()  # Get the user ID
    
    # Assign admin role
    user_role = UserRole(user_id=admin_user.id, role_id=admin_role.id)
    db.add(user_role)
    db.commit()
    db.refresh(admin_user)
    
    logger.info(f"Created admin user: {admin_email} (password: admin123)")
    return admin_user

def main():
    """Main seeding function"""
    print("Starting database seeding...")
    
    db = SessionLocal()
    try:
        # Seed roles
        print("\n1. Seeding roles...")
        created, existing = seed_roles(db)
        print(f"   [OK] Roles: {created} created, {existing} already exist")
        
        # Seed admin user
        print("\n2. Seeding admin user...")
        admin = seed_admin_user(db)
        if admin:
            print(f"   [OK] Admin user created: {admin.email}")
        else:
            print("   [SKIP] Admin user already exists")
        
        print("\n[OK] Database seeding complete!")
        print("\nDefault admin credentials:")
        print("   Email: admin@realestate.com")
        print("   Password: admin123")
        print("\n[WARNING] Change the admin password in production!")
        
    except Exception as e:
        logger.error("seeding_failed", error=str(e), exc_info=True)
        db.rollback()
        print(f"\n[ERROR] Seeding failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()

