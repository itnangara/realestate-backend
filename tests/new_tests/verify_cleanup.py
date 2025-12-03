"""
Verify that owner_id and agent_id columns have been removed
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.database import SessionLocal
from sqlalchemy import text

def verify_cleanup():
    db = SessionLocal()
    try:
        # Check for owner_id and agent_id columns
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'properties' 
            AND column_name IN ('owner_id', 'agent_id')
        """))
        remaining = [row[0] for row in result]
        
        if remaining:
            print(f"❌ Columns still exist: {remaining}")
            print("   Run: alembic upgrade head")
            return False
        else:
            print("✅ SUCCESS: owner_id and agent_id columns removed!")
            return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    verify_cleanup()

