"""add_relationship_type_to_user_properties_and_migrate_owners

Revision ID: 40d8b404f4c5
Revises: 2c5e7fc333fd
Create Date: 2025-11-27 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision: str = '40d8b404f4c5'
down_revision: Union[str, None] = '2c5e7fc333fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

relationship_enum_name = "relationshiptype"


def upgrade() -> None:
    conn = op.get_bind()
    
    # 1) Create enum type if not exists
    enum_values = ["OWNER", "TENANT", "MAINTENANCE", "AGENT", "MANAGER"]
    conn.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{relationship_enum_name}') THEN
                    CREATE TYPE {relationship_enum_name} AS ENUM ({', '.join("'%s'" % v for v in enum_values)});
                END IF;
            END
            $$;
            """
        )
    )
    
    # 2) Add relationship_type column with default value (temporary)
    op.add_column(
        'user_properties',
        sa.Column(
            'relationship_type',
            sa.Enum(*enum_values, name=relationship_enum_name),
            nullable=False,
            server_default='MAINTENANCE'  # Temporary default for existing rows
        )
    )
    
    # 3) Create index on relationship_type
    op.create_index(
        'ix_user_properties_relationship_type',
        'user_properties',
        ['relationship_type'],
        unique=False
    )
    
    # 4) Drop old unique constraint and create new one with relationship_type
    op.drop_constraint('unique_user_property', 'user_properties', type_='unique')
    op.create_unique_constraint(
        'uq_user_property_rel',
        'user_properties',
        ['user_id', 'property_id', 'relationship_type']
    )
    
    # 5) Migrate existing Property.owner_id -> user_properties with relationship_type='OWNER'
    # This is idempotent - won't create duplicates
    conn.execute(
        text(
            """
            INSERT INTO user_properties (user_id, property_id, relationship_type, created_at)
            SELECT p.owner_id, p.id, 'OWNER', COALESCE(p.created_at, NOW())
            FROM properties p
            WHERE p.owner_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM user_properties up
                  WHERE up.property_id = p.id
                    AND up.user_id = p.owner_id
                    AND up.relationship_type = 'OWNER'
              );
            """
        )
    )
    
    # 6) Update existing user_properties rows (those without relationship_type set)
    # Set them to MAINTENANCE as default (since they were likely maintenance assignments)
    conn.execute(
        text(
            """
            UPDATE user_properties
            SET relationship_type = 'MAINTENANCE'
            WHERE relationship_type IS NULL OR relationship_type = 'MAINTENANCE';
            """
        )
    )
    
    # 7) Remove server default after data migration
    op.alter_column(
        'user_properties',
        'relationship_type',
        server_default=None
    )


def downgrade() -> None:
    # Drop unique constraint
    op.drop_constraint('uq_user_property_rel', 'user_properties', type_='unique')
    op.create_unique_constraint(
        'unique_user_property',
        'user_properties',
        ['user_id', 'property_id']
    )
    
    # Drop index
    op.drop_index('ix_user_properties_relationship_type', table_name='user_properties')
    
    # Drop column
    op.drop_column('user_properties', 'relationship_type')
    
    # Drop enum type
    op.execute(text(f"DROP TYPE IF EXISTS {relationship_enum_name};"))
