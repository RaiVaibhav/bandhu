"""user_memory_summary

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_memory_summary",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("window_start", sa.Date()),
        sa.Column("window_end", sa.Date()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_memory_summary")
