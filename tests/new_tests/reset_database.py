"""
Utility script to drop and recreate the database
Run: python reset_database.py
"""
from decouple import config
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Get database URL
database_url = config('DATABASE_URL', default='')
if not database_url:
    print("ERROR: DATABASE_URL not found in .env")
    exit(1)

# Parse database URL
# Format: postgresql://user:password@host:port/database
parts = database_url.replace('postgresql://', '').split('/')
db_name = parts[-1]
connection_string = '/'.join(parts[:-1])

print(f"Dropping database: {db_name}")
print(f"Connection: {connection_string}")

try:
    # Connect to postgres database (not the target database)
    conn = psycopg2.connect(f"postgresql://{connection_string}/postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Terminate all connections to the target database
    cursor.execute(f"""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = '{db_name}'
        AND pid <> pg_backend_pid();
    """)
    
    # Drop database
    cursor.execute(f"DROP DATABASE IF EXISTS {db_name};")
    print(f"[OK] Dropped database: {db_name}")
    
    # Create database
    cursor.execute(f"CREATE DATABASE {db_name};")
    print(f"[OK] Created database: {db_name}")
    
    cursor.close()
    conn.close()
    
    print("\n[OK] Database reset complete!")
    print("Now run: alembic upgrade head")
    
except psycopg2.Error as e:
    print(f"[ERROR] Error: {e}")
    exit(1)

