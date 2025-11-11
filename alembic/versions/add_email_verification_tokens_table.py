"""Add email verification tokens table

Revision ID: add_email_verification_tokens
Revises: fix_userstatus_enum
Create Date: 2025-11-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_email_verification_tokens'
down_revision: Union[str, None] = 'fix_userstatus_enum'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create email_verification_tokens table for secure email verification.
    
    Features:
    - One-time use tokens
    - Token expiration (24 hours)
    - Cascade delete when user is deleted
    - Indexed for fast lookups
    """
    op.create_table(
        'email_verification_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for efficient queries
    op.create_index('ix_email_verification_tokens_id', 'email_verification_tokens', ['id'])
    op.create_index('ix_email_verification_tokens_user_id', 'email_verification_tokens', ['user_id'])
    op.create_index('ix_email_verification_tokens_token', 'email_verification_tokens', ['token'], unique=True)
    op.create_index('ix_email_verification_tokens_expires_at', 'email_verification_tokens', ['expires_at'])
    op.create_index('ix_email_verification_tokens_used', 'email_verification_tokens', ['used'])
    
    # Composite indexes for common query patterns
    op.create_index('idx_token_used', 'email_verification_tokens', ['token', 'used'])
    op.create_index('idx_user_unused', 'email_verification_tokens', ['user_id', 'used'])
    op.create_index('idx_expires_used', 'email_verification_tokens', ['expires_at', 'used'])


def downgrade() -> None:
    """
    Drop email_verification_tokens table.
    """
    op.drop_index('idx_expires_used', table_name='email_verification_tokens')
    op.drop_index('idx_user_unused', table_name='email_verification_tokens')
    op.drop_index('idx_token_used', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_used', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_expires_at', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_token', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_user_id', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_id', table_name='email_verification_tokens')
    op.drop_table('email_verification_tokens')

