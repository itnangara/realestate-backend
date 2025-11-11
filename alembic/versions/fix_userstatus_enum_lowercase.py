"""Fix userstatus enum to use lowercase values

Revision ID: fix_userstatus_enum
Revises: f4d15e6b8654
Create Date: 2025-11-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fix_userstatus_enum'
down_revision: Union[str, None] = 'f4d15e6b8654'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fix userstatus enum to ensure it uses lowercase values.
    
    This migration ensures the enum type matches the Python enum values
    and is compatible with SQLAlchemy's values_callable configuration.
    
    Strategy:
    1. Convert enum column to text temporarily to preserve data
    2. Drop old enum type (if it has wrong values)
    3. Create new enum type with correct lowercase values
    4. Convert text column back to enum type (with LOWER() conversion)
    """
    # Step 1: Convert enum column to text temporarily to preserve data
    # This allows us to drop the old enum type safely
    op.execute('ALTER TABLE users ALTER COLUMN status TYPE text USING status::text')
    
    # Step 2: Drop old enum type (CASCADE will handle dependencies)
    op.execute('DROP TYPE IF EXISTS userstatus CASCADE')
    
    # Step 3: Create new enum type with lowercase values (matching Python enum values)
    userstatus_enum = postgresql.ENUM(
        "pending", "active", "suspended", "banned",
        name="userstatus",
        create_type=True
    )
    userstatus_enum.create(op.get_bind(), checkfirst=True)
    
    # Step 4: Clean and validate data - ensure all values are lowercase
    op.execute("""
        UPDATE users 
        SET status = LOWER(status)
        WHERE status IS NOT NULL
        AND LOWER(status) IN ('pending', 'active', 'suspended', 'banned')
    """)
    
    # Set invalid values to 'pending' (default)
    op.execute("""
        UPDATE users 
        SET status = 'pending'
        WHERE status IS NOT NULL
        AND LOWER(status) NOT IN ('pending', 'active', 'suspended', 'banned')
    """)
    
    # Step 5: Convert text column back to enum type
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN status TYPE userstatus 
        USING LOWER(status)::userstatus
    """)


def downgrade() -> None:
    """
    Revert userstatus enum fix.
    
    Note: This will recreate the enum type, but we can't guarantee
    the exact previous state if it was incorrect.
    """
    # Convert to text
    op.execute('ALTER TABLE users ALTER COLUMN status TYPE text USING status::text')
    
    # Drop enum type
    op.execute('DROP TYPE IF EXISTS userstatus CASCADE')
    
    # Recreate with lowercase values (same as upgrade)
    userstatus_enum = postgresql.ENUM(
        "pending", "active", "suspended", "banned",
        name="userstatus",
        create_type=True
    )
    userstatus_enum.create(op.get_bind(), checkfirst=True)
    
    # Convert back to enum
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN status TYPE userstatus 
        USING LOWER(status)::userstatus
    """)

