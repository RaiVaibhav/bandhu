import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.clients.db import Base


class EvaluatorScore(Base):
    """Stage 12's output — see backend-architecture.md §4. A sampled (5-10%),
    async quality check, structurally separate from telemetry (langfuse_setup.py):
    tracing covers every request and asks "did this work technically",
    this table scores a sample of them against the MITI rubric and asks
    "was this a good response". Never read by anything in the live
    request path — purely for later review."""

    __tablename__ = "evaluator_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    checkin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_checkins.id", ondelete="CASCADE")
    )
    miti_scores: Mapped[dict | None] = mapped_column(JSONB)
    acknowledgment_complete: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
