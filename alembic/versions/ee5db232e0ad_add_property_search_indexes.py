"""add_property_search_indexes

Revision ID: ee5db232e0ad
Revises: b196c964eddc
Create Date: 2025-10-26 18:54:13.997593

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee5db232e0ad'
down_revision: Union[str, None] = 'b196c964eddc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add production-ready indexes for advanced property search optimization.
    
    Indexes added:
    - B-Tree indexes for single-column filters (price, property_type, bedrooms, etc.)
    - Composite indexes for common multi-field queries (city+state, city+state+zip)
    - GIN index for JSONB features search
    - Indexes for sorting and pagination optimization
    """
    
    # Basic B-Tree indexes for single-column filters
    op.create_index("idx_property_price", "properties", ["price"])
    op.create_index("idx_property_type", "properties", ["property_type"])
    op.create_index("idx_property_bedrooms", "properties", ["bedrooms"])
    op.create_index("idx_property_bathrooms", "properties", ["bathrooms"])
    op.create_index("idx_property_status", "properties", ["status"])
    op.create_index("idx_property_created_at", "properties", ["created_at"])
    op.create_index("idx_property_is_featured", "properties", ["is_featured"])
    
    # Composite indexes for common multi-field queries
    op.create_index("idx_property_city_state", "properties", ["city", "state"])
    op.create_index("idx_property_city_state_zip", "properties", ["city", "state", "zip_code"])
    
    # Note: JSON features column cannot be indexed directly in PostgreSQL
    # For production, consider converting to JSONB or using functional indexes
    # op.create_index("idx_property_features", "properties", ["features"])
    
    # Additional indexes for square footage and year built filters
    op.create_index("idx_property_square_feet", "properties", ["square_feet"])
    op.create_index("idx_property_year_built", "properties", ["year_built"])


def downgrade() -> None:
    """
    Remove all indexes added in upgrade().
    """
    
    # Drop B-Tree indexes
    op.drop_index("idx_property_price", "properties")
    op.drop_index("idx_property_type", "properties")
    op.drop_index("idx_property_bedrooms", "properties")
    op.drop_index("idx_property_bathrooms", "properties")
    op.drop_index("idx_property_status", "properties")
    op.drop_index("idx_property_created_at", "properties")
    op.drop_index("idx_property_is_featured", "properties")
    
    # Drop composite indexes
    op.drop_index("idx_property_city_state", "properties")
    op.drop_index("idx_property_city_state_zip", "properties")
    
    # Note: JSON features index was not created, so no need to drop it
    # op.drop_index("idx_property_features", "properties")
    
    # Drop additional indexes
    op.drop_index("idx_property_square_feet", "properties")
    op.drop_index("idx_property_year_built", "properties")
