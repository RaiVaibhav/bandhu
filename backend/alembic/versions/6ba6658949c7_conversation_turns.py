"""conversation_turns

Revision ID: 6ba6658949c7
Revises: dafaa4ec33cd
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "6ba6658949c7"
down_revision = "dafaa4ec33cd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.create_table(
        "conversation_turns",
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
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="conversation_turns_role_check"),
    )
    op.create_index(
        "conversation_turns_session_idx",
        "conversation_turns",
        ["session_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("conversation_turns_session_idx", table_name="conversation_turns")
    op.drop_table("conversation_turns")
