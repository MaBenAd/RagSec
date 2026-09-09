"""Initial PostgreSQL schema

Revision ID: 20260415_0001
Revises:
Create Date: 2026-04-15 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260415_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qa_review",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_hash", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("question_hash", name="uq_qa_review_question_hash"),
    )
    op.create_index("ix_qa_review_question_hash", "qa_review", ["question_hash"], unique=False)

    op.create_table(
        "timetables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("class_label", sa.String(length=120), nullable=False),
        sa.Column("academic_year", sa.String(length=50), nullable=False),
        sa.Column("semester", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_timetables_class_label", "timetables", ["class_label"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("class_label", sa.String(length=120), nullable=True),
        sa.Column("language", sa.String(length=5), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.create_table(
        "class_change_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("current_class_label", sa.String(length=120), nullable=True),
        sa.Column("requested_class_label", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_class_change_requests_reviewed_by", "class_change_requests", ["reviewed_by"], unique=False)
    op.create_index("ix_class_change_requests_user_id", "class_change_requests", ["user_id"], unique=False)

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=True),
        sa.Column("feedback", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"], unique=False)

    op.create_table(
        "timetable_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timetable_id", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(length=10), nullable=False),
        sa.Column("end_time", sa.String(length=10), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("professor", sa.String(length=255), nullable=True),
        sa.Column("room", sa.String(length=100), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["timetable_id"], ["timetables.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_timetable_slots_timetable_id", "timetable_slots", ["timetable_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_timetable_slots_timetable_id", table_name="timetable_slots")
    op.drop_table("timetable_slots")

    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_table("conversations")

    op.drop_index("ix_class_change_requests_user_id", table_name="class_change_requests")
    op.drop_index("ix_class_change_requests_reviewed_by", table_name="class_change_requests")
    op.drop_table("class_change_requests")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_timetables_class_label", table_name="timetables")
    op.drop_table("timetables")

    op.drop_index("ix_qa_review_question_hash", table_name="qa_review")
    op.drop_table("qa_review")
