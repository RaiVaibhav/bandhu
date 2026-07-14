"""redirect_templates

Revision ID: a1b2c3d4e5f6
Revises: 766601b8952c
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "766601b8952c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "redirect_templates",
        sa.Column("category", sa.Text(), primary_key=True),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("vetted_by", sa.Text()),
        sa.Column("vetted_date", sa.Date()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "category IN ('redirect-medical', 'redirect-disorder', 'redirect-medication', 'redirect-document')",
            name="redirect_templates_category_check",
        ),
        sa.CheckConstraint(
            "status IN ('ai-drafted', 'self-vetted', 'pending-professional-review', 'professional-reviewed')",
            name="redirect_templates_status_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("redirect_templates")
