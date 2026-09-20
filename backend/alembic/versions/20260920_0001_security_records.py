"""Add protected application records after the single inherited head.

Revision ID: 20260920_0001
Revises: 20260426_0002
"""
from alembic import op
import sqlalchemy as sa

revision = "20260920_0001"
down_revision = "20260426_0002"
branch_labels = None
depends_on = None


def upgrade():
    # Copy the frozen column definitions below; do not import mutable ORM models.
    definitions = {
        "security_memberships": [
            ("user_id", sa.Integer(), True), ("tenant", sa.String(64), False),
            ("role", sa.String(16), False), ("enabled", sa.Boolean(), False),
            ("access_version", sa.Integer(), False), ("grants_json", sa.Text(), False)],
        "security_state": [("id", sa.Integer(), True), ("corpus_version", sa.Integer(), False),
                           ("collections_json", sa.Text(), False)],
        "security_sources": [("id", sa.String(64), True), ("tenant", sa.String(64), False),
                             ("registered_by", sa.Integer(), False), ("enabled", sa.Boolean(), False)],
        "security_documents": [
            ("id", sa.String(64), True), ("tenant", sa.String(64), False), ("owner", sa.Integer(), False),
            ("source_id", sa.String(64), False), ("classification", sa.String(16), False),
            ("status", sa.String(16), False), ("version", sa.Integer(), False),
            ("access_version", sa.Integer(), False), ("original_hash", sa.String(64), False),
            ("extraction_hash", sa.String(64), False), ("text", sa.Text(), False),
            ("parser_version", sa.String(64), False), ("embedding_version", sa.String(64), False),
            ("signals_json", sa.Text(), False), ("created_at", sa.Float(), False)],
        "security_chunks": [("id", sa.String(64), True), ("document_id", sa.String(64), False),
                            ("version", sa.Integer(), False), ("text", sa.Text(), False),
                            ("content_hash", sa.String(64), False)],
        "security_tombstones": [("document_id", sa.String(64), True), ("original_hash", sa.String(64), False),
                                ("tenant", sa.String(64), False), ("revoked_at", sa.Float(), False),
                                ("cleaned", sa.Boolean(), False)],
        "security_memory": [("id", sa.String(64), True), ("tenant", sa.String(64), False),
                            ("owner", sa.Integer(), False), ("access_version", sa.Integer(), False),
                            ("text", sa.Text(), False), ("content_hash", sa.String(64), False),
                            ("provenance", sa.String(64), False), ("expires_at", sa.Float(), False)],
        "security_budgets": [("user_id", sa.Integer(), True), ("window", sa.Integer(), False),
                             ("requests", sa.Integer(), False), ("tokens", sa.Integer(), False)],
        "security_audit": [("id", sa.String(64), True), ("request_id", sa.String(64), False),
                           ("actor_id", sa.Integer(), False), ("stage", sa.String(32), False),
                           ("reason", sa.String(64), False), ("resource_ids", sa.Text(), False),
                           ("policy_version", sa.String(32), False), ("corpus_version", sa.Integer(), False),
                           ("access_version", sa.Integer(), False), ("duration_ms", sa.Float(), False),
                           ("created_at", sa.Float(), False)],
    }
    for name, columns in definitions.items():
        extras = []
        if name == "security_documents":
            extras = [sa.Column("original_path", sa.Text()), sa.Column("reviewer", sa.Integer()),
                      sa.Column("reviewed_at", sa.Float()), sa.Column("expires_at", sa.Float()),
                      sa.UniqueConstraint("tenant", "owner", "source_id", "original_hash", "classification")]
        op.create_table(name, *[sa.Column(n, t, primary_key=pk, nullable=False) for n, t, pk in columns], *extras)
    for table, column in [("security_documents", "tenant"), ("security_chunks", "document_id"),
                          ("security_audit", "request_id")]:
        op.create_index(f"ix_{table}_{column}", table, [column])
    op.execute("INSERT INTO security_state (id, corpus_version, collections_json) VALUES (1, 1, '{}')")


def downgrade():
    for name in ["audit", "budgets", "memory", "tombstones", "chunks", "documents", "sources", "state", "memberships"]:
        op.drop_table(f"security_{name}")
