"""
Setup fresh database - creates tables from models and stamps migrations
Run: python setup_fresh_database.py
"""
from app.utils.database import engine, Base
from decouple import config
import logging

# Import all models so they're registered with Base.metadata
from app.models import *  # noqa: F401, F403

# Suppress SQLAlchemy info logs
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

print("Creating all tables from models...")
Base.metadata.create_all(bind=engine)
print("[OK] All tables created from models")

print("\nStamping database to head (marking all migrations as applied)...")
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "alembic", "stamp", "head"],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print("[OK] Database stamped to head")
    print("\n[OK] Fresh database setup complete!")
    print("Your database is now ready with:")
    print("  - All tables created from models")
    print("  - All migrations marked as applied")
else:
    print(f"[ERROR] Failed to stamp database:")
    print(result.stderr)
    sys.exit(1)

