import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db import Base


class UserSession(Base):
    """The anchor table. Every other per-user table cascades from here — deleting
    a row here is the entire 14-day cleanup mechanism (see jobs/cleanup.py)."""

    __tablename__ = "user_sessions"
    __table_args__ = (Index("user_sessions_last_active_idx", "last_active_at"),)

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_crisis_card_shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
