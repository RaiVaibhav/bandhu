from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db import Base


class RedirectTemplate(Base):
    """Fixed, vetted copy for the 4 special-case categories Classify (stage 3)
    can flag — see backend-architecture.md §4 / vector-database.md §2. NOT
    embedded, direct lookup by category only: the right answer for
    "do I have depression" never depends on retrieval, it's always the same
    careful redirect. Gated by the same ingestion rule as safety_patterns,
    one tier stricter than the general content library: only
    professional-reviewed rows are eligible to load here. As of this build,
    knowledge-base/redirects/*.md is self-vetted, not professional-reviewed —
    the ingestion gate correctly blocks it, so this table has real rows only
    once that review happens. See knowledge-base/VETTING.md."""

    __tablename__ = "redirect_templates"
    __table_args__ = (
        CheckConstraint(
            "category IN ('redirect-medical', 'redirect-disorder', 'redirect-medication', 'redirect-document')",
            name="redirect_templates_category_check",
        ),
        CheckConstraint(
            "status IN ('ai-drafted', 'self-vetted', 'pending-professional-review', 'professional-reviewed')",
            name="redirect_templates_status_check",
        ),
    )

    category: Mapped[str] = mapped_column(Text, primary_key=True)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    vetted_by: Mapped[str | None] = mapped_column(Text)
    vetted_date: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
