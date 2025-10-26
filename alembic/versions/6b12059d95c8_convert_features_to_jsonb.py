"""convert_features_to_jsonb

Revision ID: 6b12059d95c8
Revises: ee5db232e0ad
Create Date: 2025-10-26 20:16:55.716860

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6b12059d95c8'
down_revision: Union[str, None] = 'ee5db232e0ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Convert features column from JSON to JSONB and create GIN index for fast searching.
    This enables efficient JSONB contains() operations for features search.
    """
    # Convert JSON to JSONB
    op.execute("ALTER TABLE properties ALTER COLUMN features TYPE jsonb USING features::jsonb")
    
    # Create GIN index for fast JSONB queries
    op.execute("CREATE INDEX idx_properties_features_gin ON properties USING GIN (features)")


def downgrade() -> None:
    """
    Revert features column from JSONB to JSON and drop GIN index.
    """
    # Drop GIN index
    op.execute("DROP INDEX IF EXISTS idx_properties_features_gin")
    
    # Convert JSONB back to JSON
    op.execute("ALTER TABLE properties ALTER COLUMN features TYPE json USING features::json")
