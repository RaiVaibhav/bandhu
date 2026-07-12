"""user_sessions

Revision ID: dafaa4ec33cd
Revises:
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "dafaa4ec33cd"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_crisis_card_shown_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("user_sessions_last_active_idx", "user_sessions", ["last_active_at"])


def downgrade() -> None:
    op.drop_index("user_sessions_last_active_idx", table_name="user_sessions")
    op.drop_table("user_sessions")
