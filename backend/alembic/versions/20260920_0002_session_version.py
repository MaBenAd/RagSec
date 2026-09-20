"""Separate login-session revocation from data and memory grants."""
from alembic import op
import sqlalchemy as sa

revision = "20260920_0002"
down_revision = "20260920_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("security_memberships", sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    op.drop_column("security_memberships", "session_version")
