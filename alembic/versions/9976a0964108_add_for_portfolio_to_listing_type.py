"""add_for_portfolio_to_listing_type

Revision ID: 9976a0964108
Revises: ca3e7a588d50
Create Date: 2025-11-08 04:36:40.809737

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9976a0964108'
down_revision: Union[str, None] = 'ca3e7a588d50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add 'for_portfolio' value to listingtype enum.
    
    Enterprise-grade migration: PostgreSQL allows adding enum values,
    but we need to check if it already exists to make the migration idempotent.
    """
    # Add for_portfolio to listingtype enum if it doesn't exist
    # PostgreSQL doesn't support IF NOT EXISTS for ALTER TYPE ADD VALUE,
    # so we use a DO block to check first
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum 
                WHERE enumlabel = 'for_portfolio' 
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'listingtype')
            ) THEN
                ALTER TYPE listingtype ADD VALUE 'for_portfolio';
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """
    Remove 'for_portfolio' from listingtype enum.
    
    Note: PostgreSQL doesn't support removing enum values directly.
    This would require:
    1. Converting column to text
    2. Dropping and recreating enum without 'for_portfolio'
    3. Converting back
    
    For safety, we'll leave it in place. If hard removal is needed,
    create a separate migration that handles the full conversion.
    """
    # PostgreSQL doesn't support removing enum values easily
    # Set any for_portfolio properties to NULL or a default value
    op.execute("""
        UPDATE properties 
        SET listing_type = NULL 
        WHERE listing_type = 'for_portfolio'
    """)
    # Note: The enum value remains in the database but is unused
