"""add_file_name_size_mime_type_to_documents

Revision ID: 7a30e2f1513a
Revises: add_file_id_uuid
Create Date: 2025-11-11 14:51:48.803672

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a30e2f1513a'
down_revision: Union[str, None] = 'add_file_id_uuid'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add missing columns to documents table: file_name, size, mime_type.
    
    These columns were missing from the original migration but are required
    by the Document model for proper document metadata storage.
    """
    # Add file_name column
    op.add_column(
        'documents',
        sa.Column('file_name', sa.String(length=255), nullable=True)
    )
    
    # Add size column
    op.add_column(
        'documents',
        sa.Column('size', sa.Integer(), nullable=True)
    )
    
    # Add mime_type column
    op.add_column(
        'documents',
        sa.Column('mime_type', sa.String(length=100), nullable=True)
    )
    
    # For existing records, set default values (if any exist)
    # In production, you'd want to backfill with actual data
    op.execute("""
        UPDATE documents 
        SET file_name = COALESCE(file_name, 'unknown'),
            size = COALESCE(size, 0),
            mime_type = COALESCE(mime_type, 'application/octet-stream')
        WHERE file_name IS NULL OR size IS NULL OR mime_type IS NULL
    """)
    
    # Make columns NOT NULL after backfilling
    op.alter_column('documents', 'file_name', nullable=False)
    op.alter_column('documents', 'size', nullable=False)
    op.alter_column('documents', 'mime_type', nullable=False)


def downgrade() -> None:
    """
    Remove file_name, size, and mime_type columns from documents table.
    """
    op.drop_column('documents', 'mime_type')
    op.drop_column('documents', 'size')
    op.drop_column('documents', 'file_name')
