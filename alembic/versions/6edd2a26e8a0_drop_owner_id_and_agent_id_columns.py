"""drop owner_id and agent_id columns

Revision ID: 6edd2a26e8a0
Revises: 
Create Date: 2025-01-27 20:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '6edd2a26e8a0'
down_revision: Union[str, None] = '968f6f552b80'  # Update after relationship_type enum migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Enterprise-grade migration: Drop owner_id and agent_id columns from properties table.
    
    This migration removes redundant foreign key columns that have been replaced
    by the unified user_properties table with relationship_type enum.
    
    Steps:
    1. Make columns nullable first (if they have NOT NULL constraint)
    2. Drop foreign key constraints
    3. Drop indexes on owner_id and agent_id
    4. Drop the columns
    """
    # Step 1: Make columns nullable first (safe operation even if already nullable)
    # This handles the case where columns have NOT NULL constraints
    # Check if columns exist before altering
    conn = op.get_bind()
    
    # Check and make owner_id nullable
    result = conn.execute(text("""
        SELECT column_name, is_nullable
        FROM information_schema.columns 
        WHERE table_name = 'properties' 
        AND column_name = 'owner_id'
    """))
    owner_id_row = result.fetchone()
    if owner_id_row:
        if owner_id_row[1] == 'NO':  # is_nullable = 'NO' means NOT NULL
            op.alter_column('properties', 'owner_id', nullable=True, existing_type=sa.Integer())
    
    # Check and make agent_id nullable
    result = conn.execute(text("""
        SELECT column_name, is_nullable
        FROM information_schema.columns 
        WHERE table_name = 'properties' 
        AND column_name = 'agent_id'
    """))
    agent_id_row = result.fetchone()
    if agent_id_row:
        if agent_id_row[1] == 'NO':  # is_nullable = 'NO' means NOT NULL
            op.alter_column('properties', 'agent_id', nullable=True, existing_type=sa.Integer())
    
    # Step 2: Drop foreign key constraints (check if they exist first)
    # Check for owner_id foreign key
    result = conn.execute(text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'properties' 
        AND constraint_name = 'properties_owner_id_fkey'
    """))
    if result.fetchone():
    op.drop_constraint('properties_owner_id_fkey', 'properties', type_='foreignkey')
    
    # Check for agent_id foreign key
    result = conn.execute(text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'properties' 
        AND constraint_name = 'properties_agent_id_fkey'
    """))
    if result.fetchone():
        op.drop_constraint('properties_agent_id_fkey', 'properties', type_='foreignkey')
    
    # Step 3: Drop indexes (check if they exist first)
    result = conn.execute(text("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'properties' 
        AND indexname = 'ix_properties_owner_id'
    """))
    if result.fetchone():
        op.drop_index('ix_properties_owner_id', table_name='properties')
    
    result = conn.execute(text("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'properties' 
        AND indexname = 'ix_properties_agent_id'
    """))
    if result.fetchone():
        op.drop_index('ix_properties_agent_id', table_name='properties')
    
    # Step 4: Drop columns (check if they exist first using raw SQL)
    conn = op.get_bind()
    
    # Check and drop owner_id
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'properties' 
        AND column_name = 'owner_id'
    """))
    if result.fetchone():
    op.drop_column('properties', 'owner_id')
    
    # Check and drop agent_id
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'properties' 
        AND column_name = 'agent_id'
    """))
    if result.fetchone():
    op.drop_column('properties', 'agent_id')


def downgrade() -> None:
    """
    Rollback: Re-add owner_id and agent_id columns.
    
    Note: This will NOT restore data - columns will be NULL.
    Data must be restored from user_properties table if needed.
    """
    # Re-add columns (nullable for safety)
    op.add_column('properties', sa.Column('owner_id', sa.Integer(), nullable=True))
    op.add_column('properties', sa.Column('agent_id', sa.Integer(), nullable=True))
    
    # Re-add indexes
    op.create_index('ix_properties_owner_id', 'properties', ['owner_id'])
    op.create_index('ix_properties_agent_id', 'properties', ['agent_id'])
    
    # Re-add foreign key constraints
    op.create_foreign_key('properties_owner_id_fkey', 'properties', 'users', ['owner_id'], ['id'])
    op.create_foreign_key('properties_agent_id_fkey', 'properties', 'users', ['agent_id'], ['id'])
