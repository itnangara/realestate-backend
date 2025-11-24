"""add_signed_and_active_lease_statuses_and_lease_signed_at

Revision ID: 20d2912e8b21
Revises: 7d2b9f287fd3
Create Date: 2025-11-21 02:57:19.691682

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20d2912e8b21'
down_revision: Union[str, None] = '7d2b9f287fd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add SIGNED and ACTIVE_LEASE statuses to applications and lease_signed_at timestamp.
    
    Enterprise-grade migration:
    - ApplicationStatus uses native_enum=False (stored as string), so new values work automatically
    - Increase VARCHAR length from 12 to 20 to accommodate "active_lease" (12 chars) and future values
    - Add lease_signed_at column for lease tracking
    - No enum migration needed since status is stored as VARCHAR
    """
    # Increase VARCHAR length to accommodate "active_lease" and future status values
    op.alter_column(
        'applications',
        'status',
        type_=sa.String(length=20),
        existing_type=sa.String(length=12),
        existing_nullable=False
    )
    
    # Add lease_signed_at column
    op.add_column(
        'applications',
        sa.Column('lease_signed_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Create index for efficient queries (finding active leases, etc.)
    op.create_index('ix_applications_lease_signed_at', 'applications', ['lease_signed_at'])
    
    # Note: ApplicationStatus enum values (SIGNED, ACTIVE_LEASE) are automatically
    # supported since the status column is VARCHAR, not a PostgreSQL enum type.
    # The Python enum change is sufficient - no database enum migration needed.


def downgrade() -> None:
    """
    Remove lease_signed_at column and index.
    
    Note: Cannot remove SIGNED/ACTIVE_LEASE from ApplicationStatus enum values
    since status is stored as VARCHAR. Applications with these statuses would
    need to be manually updated before downgrade.
    """
    op.drop_index('ix_applications_lease_signed_at', table_name='applications')
    op.drop_column('applications', 'lease_signed_at')
