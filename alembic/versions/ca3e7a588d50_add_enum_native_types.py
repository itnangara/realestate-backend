"""Add enum native types

Revision ID: ca3e7a588d50
Revises: 1b8adb9dd7ba
Create Date: 2025-11-08 01:55:36.198763

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ca3e7a588d50'
down_revision: Union[str, None] = '1b8adb9dd7ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Convert enum columns to use lowercase values.
    
    Enterprise-grade migration strategy:
    1. Convert enum columns to text (temporarily) to preserve data
    2. Drop old enum types (they may have uppercase values)
    3. Create new enum types with lowercase values
    4. Convert text columns back to new enum types (with LOWER() conversion)
    
    This ensures compatibility with SQLAlchemy's values_callable configuration.
    """
    # Step 1: Convert enum columns to text temporarily to preserve data
    # This allows us to drop the old enum types safely
    op.execute('ALTER TABLE properties ALTER COLUMN property_type TYPE text USING property_type::text')
    op.execute('ALTER TABLE properties ALTER COLUMN listing_type TYPE text USING listing_type::text')
    op.execute('ALTER TABLE properties ALTER COLUMN status TYPE text USING status::text')
    
    # Step 2: Drop old enum types (they may have uppercase or different values)
    # CASCADE will handle any dependencies
    op.execute('DROP TYPE IF EXISTS propertytype CASCADE')
    op.execute('DROP TYPE IF EXISTS listingtype CASCADE')
    op.execute('DROP TYPE IF EXISTS propertystatus CASCADE')
    
    # Step 3: Create new enum types with lowercase values
    new_property_type = postgresql.ENUM(
        "house", "apartment", "condo", "townhouse", "land", "commercial",
        "industrial", "duplex", "retail", "office", "warehouse",
        name="propertytype", create_type=True
    )
    new_property_type.create(op.get_bind(), checkfirst=True)
    
    new_listing_type = postgresql.ENUM(
        "for_sale", "for_rent", "for_lease", "for_auction",
        name="listingtype", create_type=True
    )
    new_listing_type.create(op.get_bind(), checkfirst=True)
    
    new_status_type = postgresql.ENUM(
        "draft", "pending_approval", "active", "under_offer",
        "sold", "rented", "expired", "archived", "rejected", "deleted",
        name="propertystatus", create_type=True
    )
    new_status_type.create(op.get_bind(), checkfirst=True)
    
    # Step 4: Clean and validate data before converting to enum types
    # Fix any data corruption (e.g., status column having listing_type values)
    # Set invalid values to NULL or default values
    
    # Clean property_type: ensure it's a valid property type value
    # property_type is NOT NULL, so set invalid values to 'house' (default)
    op.execute("""
        UPDATE properties 
        SET property_type = 'house' 
        WHERE property_type IS NOT NULL 
        AND LOWER(property_type) NOT IN ('house', 'apartment', 'condo', 'townhouse', 'land', 'commercial', 'industrial', 'duplex', 'retail', 'office', 'warehouse')
    """)
    
    # Clean listing_type: ensure it's a valid listing type value
    op.execute("""
        UPDATE properties 
        SET listing_type = NULL 
        WHERE listing_type IS NOT NULL 
        AND LOWER(listing_type) NOT IN ('for_sale', 'for_rent', 'for_lease', 'for_auction')
    """)
    
    # Clean status: ensure it's a valid status value (not listing_type values)
    # Fix common data corruption where status has listing_type values
    op.execute("""
        UPDATE properties 
        SET status = 'draft' 
        WHERE status IS NOT NULL 
        AND LOWER(status) NOT IN ('draft', 'pending_approval', 'active', 'under_offer', 'sold', 'rented', 'expired', 'archived', 'rejected', 'deleted')
    """)
    
    # Step 5: Convert text columns back to new enum types (with LOWER() conversion)
    # This converts any existing uppercase values to lowercase
    # Only convert valid values (invalid ones were set to NULL or default above)
    op.execute(
        'ALTER TABLE properties ALTER COLUMN property_type TYPE propertytype '
        'USING CASE WHEN property_type IS NULL THEN NULL ELSE LOWER(property_type)::propertytype END'
    )
    op.execute(
        'ALTER TABLE properties ALTER COLUMN listing_type TYPE listingtype '
        'USING CASE WHEN listing_type IS NULL THEN NULL ELSE LOWER(listing_type)::listingtype END'
    )
    op.execute(
        'ALTER TABLE properties ALTER COLUMN status TYPE propertystatus '
        'USING CASE WHEN status IS NULL THEN NULL ELSE LOWER(status)::propertystatus END'
    )


def downgrade() -> None:
    """
    Revert enum columns back to previous state.
    
    Note: This is a destructive operation. If you need to preserve data,
    you may need to create a custom downgrade that handles the conversion.
    """
    # Drop the new enum types
    # Note: PostgreSQL requires dropping all columns using the enum first
    # This downgrade assumes you're okay with data loss or have a backup
    op.execute('DROP TYPE IF EXISTS propertytype CASCADE')
    op.execute('DROP TYPE IF EXISTS listingtype CASCADE')
    op.execute('DROP TYPE IF EXISTS propertystatus CASCADE')
