"""create_user_properties_table

Revision ID: 2c5e7fc333fd
Revises: 49b85c620859
Create Date: 2025-11-27 17:10:15.705687

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c5e7fc333fd'
down_revision: Union[str, None] = '49b85c620859'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_properties table for linking users to properties
    # Used for maintenance staff and landlords property assignments
    op.create_table('user_properties',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'property_id', name='unique_user_property')
    )
    # Create indexes for performance
    op.create_index('ix_user_properties_user_id', 'user_properties', ['user_id'], unique=False)
    op.create_index('ix_user_properties_property_id', 'user_properties', ['property_id'], unique=False)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_user_properties_property_id', table_name='user_properties')
    op.drop_index('ix_user_properties_user_id', table_name='user_properties')
    # Drop table
    op.drop_table('user_properties')
