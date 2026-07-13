import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db import Base


class UserCheckin(Base):
    """One structured row per turn — not the conversation text itself
    (that's conversation_turns), but the facts about what happened: mood,
    theme, whether a suggestion was offered and whether it helped. Feeds
    both the Eligibility gate's rolling help-offer count (stage 5) and the
    Summarizer's bigger-picture narrative (stage 11). See
    backend-architecture.md §4 and vector-database.md §2."""

    __tablename__ = "user_checkins"
    __table_args__ = (
        CheckConstraint("input_mode IN ('text', 'voice')", name="user_checkins_input_mode_check"),
        Index("user_checkins_recent_idx", "session_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    mood_tag: Mapped[str | None] = mapped_column(Text)
    theme: Mapped[str | None] = mapped_column(Text)
    suggestion_entry_key: Mapped[str | None] = mapped_column(Text, ForeignKey("content_entries.entry_key"))
    suggestion_helped: Mapped[bool | None] = mapped_column(Boolean)
    # Feeds the stage-5 eligibility-gate count. close_the_loop turns stay
    # false — per the "care isn't rationed" design principle, only genuine
    # suggestion offers count against the frequency cap.
    is_help_offer: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    input_mode: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
