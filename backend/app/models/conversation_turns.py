import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db import Base


class ConversationTurn(Base):
    """The short-term conversation buffer — same-sitting memory only. See
    backend-architecture.md §2 for why this is structurally separate from
    user_memory_summary (the long-term horizon): this table holds raw text,
    read back with a 2-hour/12-row window, never summarized or shown to the
    person as a recap. ON DELETE CASCADE from user_sessions is the only
    cleanup mechanism this table needs — no separate trim job."""

    __tablename__ = "conversation_turns"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="conversation_turns_role_check"),
        Index("conversation_turns_session_idx", "session_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
