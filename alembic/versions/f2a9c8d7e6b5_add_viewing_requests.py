"""add viewing requests

Revision ID: f2a9c8d7e6b5
Revises: d5da913d312a
Create Date: 2026-07-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a9c8d7e6b5"
down_revision: Union[str, None] = "d5da913d312a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "viewing_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("requester_id", sa.Integer(), nullable=False),
        sa.Column("assigned_to_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "CONFIRMED", "DECLINED", "CANCELLED", "COMPLETED", name="viewingstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("requested_slots", sa.JSON(), nullable=False),
        sa.Column("confirmed_slot", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("response_note", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_viewing_requests_id"), "viewing_requests", ["id"], unique=False)
    op.create_index(op.f("ix_viewing_requests_property_id"), "viewing_requests", ["property_id"], unique=False)
    op.create_index(op.f("ix_viewing_requests_requester_id"), "viewing_requests", ["requester_id"], unique=False)
    op.create_index(op.f("ix_viewing_requests_assigned_to_id"), "viewing_requests", ["assigned_to_id"], unique=False)
    op.create_index(op.f("ix_viewing_requests_status"), "viewing_requests", ["status"], unique=False)
    op.create_index(op.f("ix_viewing_requests_confirmed_slot"), "viewing_requests", ["confirmed_slot"], unique=False)
    op.create_index(op.f("ix_viewing_requests_is_active"), "viewing_requests", ["is_active"], unique=False)
    op.create_index("ix_viewing_request_property_status", "viewing_requests", ["property_id", "status"], unique=False)
    op.create_index("ix_viewing_request_requester_status", "viewing_requests", ["requester_id", "status"], unique=False)
    op.create_index("ix_viewing_request_assigned_status", "viewing_requests", ["assigned_to_id", "status"], unique=False)
    op.create_index("ix_viewing_request_created_at", "viewing_requests", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_viewing_request_created_at", table_name="viewing_requests")
    op.drop_index("ix_viewing_request_assigned_status", table_name="viewing_requests")
    op.drop_index("ix_viewing_request_requester_status", table_name="viewing_requests")
    op.drop_index("ix_viewing_request_property_status", table_name="viewing_requests")
    op.drop_index(op.f("ix_viewing_requests_is_active"), table_name="viewing_requests")
    op.drop_index(op.f("ix_viewing_requests_confirmed_slot"), table_name="viewing_requests")
    op.drop_index(op.f("ix_viewing_requests_status"), table_name="viewing_requests")
    op.drop_index(op.f("ix_viewing_requests_assigned_to_id"), table_name="viewing_requests")
    op.drop_index(op.f("ix_viewing_requests_requester_id"), table_name="viewing_requests")
    op.drop_index(op.f("ix_viewing_requests_property_id"), table_name="viewing_requests")
    op.drop_index(op.f("ix_viewing_requests_id"), table_name="viewing_requests")
    op.drop_table("viewing_requests")
