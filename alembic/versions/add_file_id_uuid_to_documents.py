"""Add file_id UUID column to documents table

Revision ID: add_file_id_uuid
Revises: fix_userstatus_enum
Create Date: 2025-01-XX

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_file_id_uuid'
down_revision: Union[str, None] = 'add_email_verification_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add file_id UUID column to documents table.
    
    This column provides a UUID for external API exposure while keeping
    the integer id for internal DB references and relations.
    
    Enterprise-grade approach:
    - id (int): DB primary key, internal references, relations
    - file_id (UUID): Optional external reference, safe for public URLs or API exposure
    """
    # Add file_id column with UUID type
    op.add_column(
        'documents',
        sa.Column('file_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    
    # Generate UUIDs for existing records
    op.execute("""
        UPDATE documents 
        SET file_id = gen_random_uuid()
        WHERE file_id IS NULL
    """)
    
    # Make column NOT NULL and add unique constraint
    op.alter_column('documents', 'file_id', nullable=False)
    op.create_unique_constraint('uq_documents_file_id', 'documents', ['file_id'])
    
    # Add index for UUID lookups (external API exposure)
    op.create_index('idx_documents_file_id', 'documents', ['file_id'])
    
    # Add default UUID generation for new records
    op.execute("""
        ALTER TABLE documents 
        ALTER COLUMN file_id 
        SET DEFAULT gen_random_uuid()
    """)


def downgrade() -> None:
    """
    Remove file_id UUID column from documents table.
    """
    op.drop_index('idx_documents_file_id', table_name='documents')
    op.drop_constraint('uq_documents_file_id', 'documents', type_='unique')
    op.drop_column('documents', 'file_id')

