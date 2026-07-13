"""user_checkins

Revision ID: 766601b8952c
Revises: 039e3fcaf65d
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "766601b8952c"
down_revision = "039e3fcaf65d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_checkins",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mood_tag", sa.Text(), nullable=True),
        sa.Column("theme", sa.Text(), nullable=True),
        sa.Column("suggestion_entry_key", sa.Text(), sa.ForeignKey("content_entries.entry_key"), nullable=True),
        sa.Column("suggestion_helped", sa.Boolean(), nullable=True),
        sa.Column("is_help_offer", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("input_mode", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("input_mode IN ('text', 'voice')", name="user_checkins_input_mode_check"),
    )
    op.create_index(
        "user_checkins_recent_idx",
        "user_checkins",
        ["session_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("user_checkins_recent_idx", table_name="user_checkins")
    op.drop_table("user_checkins")
