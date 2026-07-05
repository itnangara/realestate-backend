"""rename REVIEWING to IN_REVIEW in maintenance requests

Revision ID: d5da913d312a
Revises: 6edd2a26e8a0
Create Date: 2025-12-16 22:41:54.758493

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5da913d312a'
down_revision: Union[str, None] = '6edd2a26e8a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE maintenance_requests SET status = 'IN_REVIEW' WHERE status = 'REVIEWING';")
    op.execute("UPDATE maintenance_status_history SET new_status = 'IN_REVIEW' WHERE new_status = 'REVIEWING';")
    op.execute("UPDATE maintenance_status_history SET old_status = 'IN_REVIEW' WHERE old_status = 'REVIEWING';")

def downgrade() -> None:
    op.execute("UPDATE maintenance_requests SET status = 'REVIEWING' WHERE status = 'IN_REVIEW';")
    op.execute("UPDATE maintenance_status_history SET new_status = 'REVIEWING' WHERE old_status = 'IN_REVIEW';")
    op.execute("UPDATE maintenance_status_history SET old_status = 'REVIEWING' WHERE old_status = 'IN_REVIEW';")
