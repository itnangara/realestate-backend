"""update_relationship_type_enum_to_new_spec

Revision ID: 968f6f552b80
Revises: 40d8b404f4c5
Create Date: 2025-11-27 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision: str = '968f6f552b80'
down_revision: Union[str, None] = '40d8b404f4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

relationship_enum_name = "relationshiptype"


def upgrade() -> None:
    conn = op.get_bind()
    
    # New enum values per spec
    new_enum_values = ["BUYER", "SELLER", "AGENT", "LANDLORD", "TENANT", "INVESTOR", "ADMIN", "MAINTENANCE_STAFF"]
    
    # Step 1: Create temporary column with text type to hold migrated values
    conn.execute(text("""
        ALTER TABLE user_properties 
        ADD COLUMN relationship_type_temp TEXT;
    """))
    
    # Step 2: Migrate data: OWNER -> LANDLORD, MAINTENANCE -> MAINTENANCE_STAFF
    conn.execute(text("""
        UPDATE user_properties
        SET relationship_type_temp = CASE
            WHEN relationship_type::text = 'OWNER' THEN 'LANDLORD'
            WHEN relationship_type::text = 'MAINTENANCE' THEN 'MAINTENANCE_STAFF'
            ELSE relationship_type::text
        END;
    """))
    
    # Step 3: Drop old enum column and constraint
    conn.execute(text("""
        ALTER TABLE user_properties DROP COLUMN relationship_type;
    """))
    
    # Step 4: Drop old enum type and create new one
    conn.execute(text(f"""
        DO $$
        BEGIN
            DROP TYPE IF EXISTS {relationship_enum_name} CASCADE;
            CREATE TYPE {relationship_enum_name} AS ENUM ({', '.join(f"'{v}'" for v in new_enum_values)});
        END
        $$;
    """))
    
    # Step 5: Add new column with new enum type
    conn.execute(text(f"""
        ALTER TABLE user_properties 
        ADD COLUMN relationship_type {relationship_enum_name} NOT NULL DEFAULT 'MAINTENANCE_STAFF';
    """))
    
    # Step 6: Copy data from temp column
    conn.execute(text("""
        UPDATE user_properties
        SET relationship_type = relationship_type_temp::relationshiptype;
    """))
    
    # Step 7: Drop temp column
    conn.execute(text("""
        ALTER TABLE user_properties DROP COLUMN relationship_type_temp;
    """))
    
    # Step 8: Recreate unique constraint
    conn.execute(text("""
        ALTER TABLE user_properties 
        ADD CONSTRAINT uq_user_property_rel 
        UNIQUE (user_id, property_id, relationship_type);
    """))
    
    # Step 9: Ensure all Property.owner_id entries are migrated to LANDLORD
    conn.execute(text("""
        INSERT INTO user_properties (user_id, property_id, relationship_type, created_at)
        SELECT p.owner_id, p.id, 'LANDLORD', COALESCE(p.created_at, NOW())
        FROM properties p
        WHERE p.owner_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM user_properties up
              WHERE up.property_id = p.id
                AND up.user_id = p.owner_id
                AND up.relationship_type = 'LANDLORD'
          );
    """))


def downgrade() -> None:
    conn = op.get_bind()
    
    # Migrate data back
    conn.execute(text("""
        UPDATE user_properties
        SET relationship_type = 'OWNER'
        WHERE relationship_type = 'LANDLORD';
    """))
    
    conn.execute(text("""
        UPDATE user_properties
        SET relationship_type = 'MAINTENANCE'
        WHERE relationship_type = 'MAINTENANCE_STAFF';
    """))
    
    # Revert enum type
    old_enum_values = ["OWNER", "TENANT", "MAINTENANCE", "AGENT", "MANAGER"]
    conn.execute(text(f"""
        DO $$
        BEGIN
            DROP TYPE IF EXISTS {relationship_enum_name} CASCADE;
            CREATE TYPE {relationship_enum_name} AS ENUM ({', '.join(f"'{v}'" for v in old_enum_values)});
        END
        $$;
    """))
    
    op.alter_column(
        'user_properties',
        'relationship_type',
        type_=sa.Enum(*old_enum_values, name=relationship_enum_name),
        existing_nullable=False
    )
