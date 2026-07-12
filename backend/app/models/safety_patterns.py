import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db import Base


class SafetyPattern(Base):
    """Stage 2's match source — see backend-architecture.md §4. Deliberately
    not vectorized: pattern matching needs to be exact/auditable, not
    similarity-based (vector-database.md §2). Gated by the same ingestion
    rule as redirect_templates, one tier stricter than the general content
    library: only professional-reviewed rows are eligible to load here. As
    of this build, the crisis-language-patterns.md source list is
    self-vetted, not professional-reviewed — the ingestion gate correctly
    blocks it, so this table has real rows only once that review happens.
    See knowledge-base/VETTING.md."""

    __tablename__ = "safety_patterns"
    __table_args__ = (
        CheckConstraint("pattern_type IN ('direct', 'indirect', 'self-harm')", name="safety_patterns_type_check"),
        CheckConstraint(
            "status IN ('ai-drafted', 'self-vetted', 'pending-professional-review', 'professional-reviewed')",
            name="safety_patterns_status_check",
        ),
        Index("safety_patterns_active_idx", "active", postgresql_where=text("active")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_type: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
