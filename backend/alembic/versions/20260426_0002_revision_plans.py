"""Add revision plans

Revision ID: 20260426_0002
Revises: 20260415_0001
Create Date: 2026-04-26 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_0002"
down_revision = "20260419_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revision_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("modules_json", sa.Text(), nullable=False),
        sa.Column("availability_json", sa.Text(), nullable=False),
        sa.Column("sessions_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_revision_plans_user_id", "revision_plans", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_revision_plans_user_id", table_name="revision_plans")
    op.drop_table("revision_plans")
