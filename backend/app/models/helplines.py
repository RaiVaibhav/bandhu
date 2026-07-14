import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db import Base


class Helpline(Base):
    """The Crisis response branch's source of real phone numbers — see
    backend-architecture.md §4 stage 2 / vector-database.md §2. Gated
    differently from every other high-risk table: `verified_at` is a live
    phone-verification fact (someone dialed the number and confirmed it
    connects), not a clinical-content review, so this table doesn't go
    through the professional-review ingestion gate the way
    safety_patterns/redirect_templates do — see knowledge-base/safety/
    helpline-directory.md for exactly what was and wasn't checked, and when.
    Application code must refuse to serve a row where verified_at is NULL —
    that's an application-level guarantee, not a database constraint,
    because the schema can't know how stale is too stale."""

    __tablename__ = "helplines"
    __table_args__ = (CheckConstraint("audience IN ('general', 'minor')", name="helplines_audience_check"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    org_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone_number: Mapped[str] = mapped_column(Text, nullable=False)
    hours: Mapped[str | None] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(Text, nullable=False, server_default="general")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
