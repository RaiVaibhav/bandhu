import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, CheckConstraint, Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db import Base

# Placeholder — confirm against the actual Voyage (or alternative) embedding
# model's real dimension before this table is ever seeded for real. See
# vector-database.md §5 open items.
EMBEDDING_DIMENSION = 1024


class ContentEntry(Base):
    """The vetted content library Retrieval (stage 6) queries — see
    vector-database.md §2/§4. Built now, ahead of stage 6 itself, only to
    give user_checkins.suggestion_entry_key a real foreign key target
    instead of quietly weakening a design decision that's already settled
    (single-database means this FK is real now, not an application-level
    promise — see vector-database.md §5). Retrieval/ingestion logic is not
    implemented yet; this is the table shape only."""

    __tablename__ = "content_entries"
    __table_args__ = (
        CheckConstraint("risk_tier IN ('low', 'medium', 'high')", name="content_entries_risk_tier_check"),
        CheckConstraint(
            "status IN ('ai-drafted', 'self-vetted', 'pending-professional-review', 'professional-reviewed')",
            name="content_entries_status_check",
        ),
        # Never embed anything above 'medium' risk into this table — enforced
        # at the database level, not just in application code.
        CheckConstraint("risk_tier != 'high'", name="no_high_risk_embedding"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    entry_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    risk_tier: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source_citation: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    # Generated column — populated by Postgres itself, not written by the app.
    # See migration for the actual GENERATED ALWAYS AS expression.
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)
    vetted_by: Mapped[str | None] = mapped_column(Text)
    vetted_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
