"""increase_application_status_varchar_length_for_active_lease

Revision ID: dee41b99e6af
Revises: 20d2912e8b21
Create Date: 2025-11-21 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dee41b99e6af'
down_revision: Union[str, None] = '20d2912e8b21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Increase applications.status VARCHAR length from 12 to 20.
    
    Required because "active_lease" is 12 characters, and we need room for future status values.
    """
    op.alter_column(
        'applications',
        'status',
        type_=sa.String(length=20),
        existing_type=sa.String(length=12),
        existing_nullable=False
    )


def downgrade() -> None:
    """
    Revert VARCHAR length back to 12.
    
    Warning: This will fail if any applications have status values longer than 12 characters.
    """
    op.alter_column(
        'applications',
        'status',
        type_=sa.String(length=12),
        existing_type=sa.String(length=20),
        existing_nullable=False
    )
