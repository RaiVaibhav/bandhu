"""content_entries

Revision ID: 039e3fcaf65d
Revises: dfe53df3a579
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "039e3fcaf65d"
down_revision = "dfe53df3a579"
branch_labels = None
depends_on = None

EMBEDDING_DIMENSION = 1024  # placeholder — see vector-database.md §5


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    op.create_table(
        "content_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("entry_key", sa.Text(), nullable=False, unique=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("language", sa.Text(), nullable=False, server_default="en"),
        sa.Column("risk_tier", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source_citation", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=True,
        ),
        sa.Column("vetted_by", sa.Text(), nullable=True),
        sa.Column("vetted_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("risk_tier IN ('low', 'medium', 'high')", name="content_entries_risk_tier_check"),
        sa.CheckConstraint(
            "status IN ('ai-drafted', 'self-vetted', 'pending-professional-review', 'professional-reviewed')",
            name="content_entries_status_check",
        ),
        sa.CheckConstraint("risk_tier != 'high'", name="no_high_risk_embedding"),
    )

    op.create_index("content_entries_category_idx", "content_entries", ["category"])
    op.create_index("content_entries_tags_idx", "content_entries", ["tags"], postgresql_using="gin")
    op.create_index("content_entries_lang_idx", "content_entries", ["language"])
    op.create_index("content_entries_search_idx", "content_entries", ["search_vector"], postgresql_using="gin")
    op.execute(
        "CREATE INDEX content_entries_embedding_idx ON content_entries "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("content_entries_embedding_idx", table_name="content_entries")
    op.drop_index("content_entries_search_idx", table_name="content_entries")
    op.drop_index("content_entries_lang_idx", table_name="content_entries")
    op.drop_index("content_entries_tags_idx", table_name="content_entries")
    op.drop_index("content_entries_category_idx", table_name="content_entries")
    op.drop_table("content_entries")
