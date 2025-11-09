"""Add role onboarding tables and user status

Revision ID: f4d15e6b8654
Revises: 9976a0964108
Create Date: 2025-11-09 02:30:29.844788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f4d15e6b8654'
down_revision: Union[str, None] = '9976a0964108'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add role onboarding tables and user status enum.
    
    Creates:
    - userstatus enum (pending, active, suspended, banned)
    - role_requests table
    - kyc_requests table
    - documents table
    - audit_logs table
    - user_limits table
    - Adds status column to users table
    """
    
    # Step 1: Create enum types (only if they don't exist)
    # Use raw SQL to check existence to avoid duplicate object errors
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE userstatus AS ENUM ('pending', 'active', 'suspended', 'banned');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE rolerequeststatus AS ENUM ('pending', 'in_review', 'approved', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE kycrequeststatus AS ENUM ('not_started', 'submitted', 'in_review', 'approved', 'rejected', 'error');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE documenttype AS ENUM ('id_front', 'id_back', 'proof_of_address', 'company_doc');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE documentstatus AS ENUM ('pending', 'uploaded', 'verified', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create enum objects for use in table definitions
    userstatus_enum = postgresql.ENUM(
        "pending", "active", "suspended", "banned",
        name="userstatus",
        create_type=False  # Already created above
    )
    
    rolerequeststatus_enum = postgresql.ENUM(
        "pending", "in_review", "approved", "rejected",
        name="rolerequeststatus",
        create_type=False  # Already created above
    )
    
    kycrequeststatus_enum = postgresql.ENUM(
        "not_started", "submitted", "in_review", "approved", "rejected", "error",
        name="kycrequeststatus",
        create_type=False  # Already created above
    )
    
    documenttype_enum = postgresql.ENUM(
        "id_front", "id_back", "proof_of_address", "company_doc",
        name="documenttype",
        create_type=False  # Already created above
    )
    
    documentstatus_enum = postgresql.ENUM(
        "pending", "uploaded", "verified", "rejected",
        name="documentstatus",
        create_type=False  # Already created above
    )
    
    # Step 2: Add status column to users table
    op.add_column('users', sa.Column('status', userstatus_enum, server_default='pending', nullable=False))
    op.create_index('ix_users_status', 'users', ['status'])
    
    # Step 3: Create role_requests table
    op.create_table(
        'role_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('requested_roles', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('status', rolerequeststatus_enum, server_default='pending', nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('attachments', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('trust_score', sa.Float(), server_default='0.0', nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_role_requests_user_id', 'role_requests', ['user_id'])
    op.create_index('ix_role_requests_status', 'role_requests', ['status'])
    op.create_index('ix_role_requests_requested_at', 'role_requests', ['requested_at'])
    op.create_index('idx_role_requests_user_status', 'role_requests', ['user_id', 'status'])
    op.create_index('idx_role_requests_status_requested_at', 'role_requests', ['status', 'requested_at'])
    
    # Step 4: Create kyc_requests table
    op.create_table(
        'kyc_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider_reference', sa.String(length=255), nullable=True),
        sa.Column('status', kycrequeststatus_enum, server_default='not_started', nullable=False),
        sa.Column('verdict', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('raw_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_reference')
    )
    op.create_index('ix_kyc_requests_user_id', 'kyc_requests', ['user_id'])
    op.create_index('ix_kyc_requests_provider_reference', 'kyc_requests', ['provider_reference'])
    op.create_index('ix_kyc_requests_status', 'kyc_requests', ['status'])
    op.create_index('idx_kyc_requests_user_status', 'kyc_requests', ['user_id', 'status'])
    op.create_index('idx_kyc_requests_provider_ref', 'kyc_requests', ['provider_reference'])
    
    # Step 5: Create documents table
    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', documenttype_enum, nullable=False),
        sa.Column('s3_key', sa.String(length=255), nullable=False),
        sa.Column('status', documentstatus_enum, server_default='pending', nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('s3_key')
    )
    op.create_index('ix_documents_user_id', 'documents', ['user_id'])
    op.create_index('ix_documents_type', 'documents', ['type'])
    op.create_index('ix_documents_status', 'documents', ['status'])
    op.create_index('idx_documents_user_type', 'documents', ['user_id', 'type'])
    op.create_index('idx_documents_user_status', 'documents', ['user_id', 'status'])
    
    # Step 6: Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=255), nullable=False),
        sa.Column('target_type', sa.String(length=50), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('request_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_target_type', 'audit_logs', ['target_type'])
    op.create_index('ix_audit_logs_target_id', 'audit_logs', ['target_id'])
    op.create_index('ix_audit_logs_request_id', 'audit_logs', ['request_id'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('idx_audit_logs_actor_action', 'audit_logs', ['actor_id', 'action'])
    op.create_index('idx_audit_logs_target', 'audit_logs', ['target_type', 'target_id'])
    op.create_index('idx_audit_logs_request_id', 'audit_logs', ['request_id'])
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'])
    
    # Step 7: Create user_limits table
    op.create_table(
        'user_limits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('listings_remaining_today', sa.Integer(), server_default='0', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='unique_user_limit')
    )
    op.create_index('ix_user_limits_user_id', 'user_limits', ['user_id'])


def downgrade() -> None:
    """
    Remove role onboarding tables and user status enum.
    """
    # Drop tables in reverse order
    op.drop_table('user_limits')
    op.drop_table('audit_logs')
    op.drop_table('documents')
    op.drop_table('kyc_requests')
    op.drop_table('role_requests')
    
    # Remove status column from users
    op.drop_index('ix_users_status', table_name='users')
    op.drop_column('users', 'status')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS documentstatus CASCADE')
    op.execute('DROP TYPE IF EXISTS documenttype CASCADE')
    op.execute('DROP TYPE IF EXISTS kycrequeststatus CASCADE')
    op.execute('DROP TYPE IF EXISTS rolerequeststatus CASCADE')
    op.execute('DROP TYPE IF EXISTS userstatus CASCADE')

