"""add_proof_of_income_and_employer_letter_to_documenttype_enum

Revision ID: 7d2b9f287fd3
Revises: 9c065c1a64ea
Create Date: 2025-11-20 23:30:03.700130

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d2b9f287fd3'
down_revision: Union[str, None] = '9c065c1a64ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add missing document types to documenttype enum.
    
    Adds:
    - proof_of_income (required for tenant onboarding)
    - employer_letter (required for tenant onboarding)
    
    These values were added to the Python enum but the database enum wasn't updated.
    """
    # PostgreSQL: Add enum values to existing documenttype enum
    # Check if values exist first to make migration idempotent
    
    # Add proof_of_income (only if it doesn't exist)
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum 
                WHERE enumlabel = 'proof_of_income' 
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'documenttype')
            ) THEN
                ALTER TYPE documenttype ADD VALUE 'proof_of_income';
            END IF;
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    # Add employer_letter (only if it doesn't exist)
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum 
                WHERE enumlabel = 'employer_letter' 
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'documenttype')
            ) THEN
                ALTER TYPE documenttype ADD VALUE 'employer_letter';
            END IF;
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    """
    Remove proof_of_income and employer_letter from documenttype enum.
    
    Note: PostgreSQL doesn't support removing enum values directly.
    This would require recreating the enum type, which is complex and risky.
    For production, consider this a one-way migration or implement a more
    sophisticated downgrade that recreates the enum.
    """
    # PostgreSQL doesn't support removing enum values
    # This is a one-way migration in practice
    # If you need to downgrade, you'd need to:
    # 1. Create a new enum without these values
    # 2. Update all columns to use the new enum
    # 3. Drop the old enum
    # This is complex and risky, so we leave it as a no-op
    pass
