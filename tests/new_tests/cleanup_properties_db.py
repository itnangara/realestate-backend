"""
Script to clean up properties database for unified N:M model adoption.

This script:
1. Truncates tables (dev environment only)
2. Applies Alembic migrations to drop owner_id/agent_id columns
3. Verifies the cleanup
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.database import SessionLocal, engine
from sqlalchemy import text
from alembic.config import Config
from alembic import command

def cleanup_database():
    """Clean up database tables and apply migrations"""
    db = SessionLocal()
    try:
        print("=" * 60)
        print("DATABASE CLEANUP FOR UNIFIED N:M MODEL")
        print("=" * 60)
        
        # Step 1: Truncate tables (dev environment only)
        print("\n1. Truncating tables...")
        tables_to_truncate = [
            'leases',
            'maintenance_requests',
            'user_properties',
            'properties',
        ]
        
        for table in tables_to_truncate:
            try:
                db.execute(text(f'TRUNCATE TABLE {table} CASCADE'))
                print(f"  ✓ Truncated: {table}")
            except Exception as e:
                print(f"  ⚠ Could not truncate {table}: {e}")
        
        db.commit()
        print("\n✓ Tables truncated successfully")
        
        # Step 2: Apply Alembic migrations
        print("\n2. Applying Alembic migrations...")
        alembic_cfg = Config('alembic.ini')
        try:
            command.upgrade(alembic_cfg, "head")
            print("  ✓ Migrations applied successfully")
        except Exception as e:
            print(f"  ⚠ Migration error: {e}")
            print("  → You may need to run: alembic upgrade head")
        
        # Step 3: Verify cleanup
        print("\n3. Verifying cleanup...")
        
        # Check if owner_id column exists
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'properties' 
            AND column_name IN ('owner_id', 'agent_id')
        """))
        remaining_columns = [row[0] for row in result]
        
        if remaining_columns:
            print(f"  ⚠ WARNING: Columns still exist: {remaining_columns}")
            print("  → Run migration manually: alembic upgrade head")
        else:
            print("  ✓ owner_id and agent_id columns removed")
        
        # Check table counts
        for table in ['properties', 'user_properties']:
            count = db.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
            print(f"  ✓ {table}: {count} rows")
        
        print("\n" + "=" * 60)
        print("CLEANUP COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_database()

