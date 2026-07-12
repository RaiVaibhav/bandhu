"""safety_patterns

Revision ID: dfe53df3a579
Revises: 6ba6658949c7
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "dfe53df3a579"
down_revision = "6ba6658949c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "safety_patterns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("pattern_type", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False, server_default="en"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("pattern_type IN ('direct', 'indirect', 'self-harm')", name="safety_patterns_type_check"),
        sa.CheckConstraint(
            "status IN ('ai-drafted', 'self-vetted', 'pending-professional-review', 'professional-reviewed')",
            name="safety_patterns_status_check",
        ),
    )
    op.create_index(
        "safety_patterns_active_idx",
        "safety_patterns",
        ["active"],
        postgresql_where=sa.text("active"),
    )


def downgrade() -> None:
    op.drop_index("safety_patterns_active_idx", table_name="safety_patterns")
    op.drop_table("safety_patterns")
