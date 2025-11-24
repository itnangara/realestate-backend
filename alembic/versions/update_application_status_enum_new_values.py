"""Update ApplicationStatus enum with draft submitted reviewed needs_info

Revision ID: update_app_status_enum
Revises: ad12045f2cf0
Create Date: 2025-11-22 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'ad12045f2cf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Update ApplicationStatus enum to include new values and migrate existing data.
    
    Enterprise-grade migration strategy:
    1. Since native_enum=False, status is stored as VARCHAR, so we can update data directly
    2. Update existing data: 'pending' → 'draft', 'under_review' → 'needs_info'
    3. Update enum definition to include new values
    
    New status values:
    - draft (replaces pending)
    - submitted (new)
    - reviewed (new)
    - needs_info (replaces under_review)
    """
    # Step 1: Update existing data to new status values
    # Map old values to new values
    op.execute("""
        UPDATE applications 
        SET status = 'draft' 
        WHERE status = 'pending'
    """)
    
    op.execute("""
        UPDATE applications 
        SET status = 'needs_info' 
        WHERE status = 'under_review'
    """)
    
    # Step 2: Update enum definition to include all new values
    # Since native_enum=False, we're just updating the constraint/validation
    # The actual storage is VARCHAR, so we need to alter the column type
    op.alter_column('applications', 'status',
               existing_type=sa.Enum('pending', 'approved', 'rejected', 'withdrawn', 'under_review', 'signed', 'active_lease', name='applicationstatus', native_enum=False),
               type_=sa.Enum('draft', 'submitted', 'reviewed', 'approved', 'rejected', 'needs_info', 'withdrawn', 'signed', 'active_lease', name='applicationstatus', native_enum=False),
               existing_nullable=False)


def downgrade() -> None:
    """
    Revert ApplicationStatus enum to previous values.
    
    Warning: This will fail if any applications have the new status values
    (draft, submitted, reviewed, needs_info) that don't map to old values.
    """
    # Step 1: Map new values back to old values where possible
    # draft → pending
    op.execute("""
        UPDATE applications 
        SET status = 'pending' 
        WHERE status = 'draft'
    """)
    
    # needs_info → under_review
    op.execute("""
        UPDATE applications 
        SET status = 'under_review' 
        WHERE status = 'needs_info'
    """)
    
    # submitted/reviewed → pending (best approximation)
    op.execute("""
        UPDATE applications 
        SET status = 'pending' 
        WHERE status IN ('submitted', 'reviewed')
    """)
    
    # Step 2: Revert enum definition
    op.alter_column('applications', 'status',
               existing_type=sa.Enum('draft', 'submitted', 'reviewed', 'approved', 'rejected', 'needs_info', 'withdrawn', 'signed', 'active_lease', name='applicationstatus', native_enum=False),
               type_=sa.Enum('pending', 'approved', 'rejected', 'withdrawn', 'under_review', 'signed', 'active_lease', name='applicationstatus', native_enum=False),
               existing_nullable=False)

