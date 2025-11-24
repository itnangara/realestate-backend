"""add_leases_and_lease_signatures_tables

Revision ID: dac521e361af
Revises: b8c9d0e1f2a3
Create Date: 2025-11-24 13:16:12.900626

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'dac521e361af'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create leases and lease_signatures tables"""
    
    # Create leases table
    op.create_table(
        'leases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('landlord_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('rent', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('deposit', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('terms', sa.Text(), nullable=True),
        sa.Column('clauses', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['landlord_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('rent >= 0', name='chk_rent_nonnegative'),
        sa.CheckConstraint('deposit >= 0', name='chk_deposit_nonnegative')
    )
    
    # Create indexes for leases
    op.create_index('ix_lease_application_id', 'leases', ['application_id'], unique=False)
    op.create_index('ix_lease_property_id', 'leases', ['property_id'], unique=False)
    op.create_index('ix_lease_status', 'leases', ['status'], unique=False)
    op.create_index('ix_lease_landlord_id', 'leases', ['landlord_id'], unique=False)
    op.create_index('ix_lease_tenant_id', 'leases', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_leases_id'), 'leases', ['id'], unique=False)
    
    # Create lease_signatures table
    op.create_table(
        'lease_signatures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lease_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('signature_text', sa.Text(), nullable=True),
        sa.Column('signed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('method', sa.String(length=50), nullable=False, server_default='manual'),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['lease_id'], ['leases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lease_id', 'user_id', name='ix_lease_signature_lease_user')
    )
    
    # Create indexes for lease_signatures
    op.create_index(op.f('ix_lease_signatures_id'), 'lease_signatures', ['id'], unique=False)
    op.create_index(op.f('ix_lease_signatures_lease_id'), 'lease_signatures', ['lease_id'], unique=False)
    op.create_index(op.f('ix_lease_signatures_user_id'), 'lease_signatures', ['user_id'], unique=False)


def downgrade() -> None:
    """Drop leases and lease_signatures tables"""
    op.drop_index(op.f('ix_lease_signatures_user_id'), table_name='lease_signatures')
    op.drop_index(op.f('ix_lease_signatures_lease_id'), table_name='lease_signatures')
    op.drop_index(op.f('ix_lease_signatures_id'), table_name='lease_signatures')
    op.drop_table('lease_signatures')
    op.drop_index(op.f('ix_leases_id'), table_name='leases')
    op.drop_index('ix_lease_tenant_id', table_name='leases')
    op.drop_index('ix_lease_landlord_id', table_name='leases')
    op.drop_index('ix_lease_status', table_name='leases')
    op.drop_index('ix_lease_property_id', table_name='leases')
    op.drop_index('ix_lease_application_id', table_name='leases')
    op.drop_table('leases')
