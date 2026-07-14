import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db import Base


class UserMemorySummary(Base):
    """The long-term memory horizon — see backend-architecture.md §2. One row
    per session, overwritten (not appended) each time the Summarizer (stage
    11) runs. Structurally separate from conversation_turns: this holds a
    synthesized narrative, never a verbatim quote, and is read by the
    Orchestrator (stage 7) via Memory read (stage 4) as a block inside the
    `system` prompt — never the `messages` array — so it can't come out
    looking like something just said."""

    __tablename__ = "user_memory_summary"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_sessions.session_id", ondelete="CASCADE"), primary_key=True
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[date | None] = mapped_column(Date)
    window_end: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
