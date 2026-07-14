from datetime import datetime, timedelta, timezone
from uuid import UUID

from opentelemetry import trace
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import telemetry_config
from app.models.conversation_turns import ConversationTurn
from app.models.user_memory_summary import UserMemorySummary
from app.telemetry.langfuse_setup import traced

CONVERSATION_WINDOW = timedelta(hours=2)
CONVERSATION_TURN_LIMIT = 12


class MemoryReadResult(BaseModel):
    """Stage 4's combined output — see backend-architecture.md §2/§4. Both
    horizons, read together: the short-term buffer (this sitting only) and
    the long-term rolling narrative the Summarizer maintains."""

    summary_text: str | None
    recent_turns: list[dict]


@traced("memory.read")
async def read_recent_turns(db: AsyncSession, session_id: UUID) -> list[dict]:
    """Same-sitting conversation buffer — see backend-architecture.md §2.
    Returns the most recent turns, oldest-first, ready to drop straight into
    Claude's `messages` array. Comes back empty once the person has been
    away longer than the window; the long-term summary
    (user_memory_summary) is what carries continuity across that gap
    instead, never a raw quote from an earlier sitting."""
    cutoff = datetime.now(timezone.utc) - CONVERSATION_WINDOW

    result = await db.execute(
        select(ConversationTurn.role, ConversationTurn.content)
        .where(
            ConversationTurn.session_id == session_id,
            ConversationTurn.created_at > cutoff,
        )
        .order_by(ConversationTurn.created_at.desc())
        .limit(CONVERSATION_TURN_LIMIT)
    )
    # DESC + LIMIT gets the most recent N; reverse back to chronological
    # order for the messages array — see backend-architecture.md §2 for why
    # a plain ORDER BY ASC LIMIT would silently return the wrong slice.
    rows = list(reversed(result.all()))

    turns = [{"role": row.role, "content": row.content} for row in rows]
    trace.get_current_span().set_attribute("memory.turns_read", len(turns))
    return turns


@traced("memory.read_summary")
async def read_summary(db: AsyncSession, session_id: UUID) -> str | None:
    """Long-term rolling narrative — see backend-architecture.md §2. One row
    per session, written periodically by the Summarizer (stage 11), never
    per-turn. None on a session's first visit, before any pattern exists to
    summarize — Orchestrator/Generate already treat that as "No prior
    context yet." (generate.py), not a special case here."""
    result = await db.execute(
        select(UserMemorySummary.summary_text).where(UserMemorySummary.session_id == session_id)
    )
    summary_text = result.scalar_one_or_none()
    trace.get_current_span().set_attribute("memory.summary_present", summary_text is not None)
    return summary_text


@traced("pipeline.memory_read")
async def read_memory(db: AsyncSession, session_id: UUID) -> MemoryReadResult:
    """Stage 4 — combines both memory horizons into the one shape the
    Orchestrator (stage 7) and Generate (stage 8) actually consume. Kept as
    a thin combinator over the two reads above (rather than merging their
    queries) so each horizon stays independently testable, same reasoning
    as every other stage boundary in this pipeline."""
    summary_text = await read_summary(db, session_id)
    recent_turns = await read_recent_turns(db, session_id)
    if telemetry_config.message_content:
        trace.get_current_span().set_attribute("memory.summary_text", summary_text or "")
    return MemoryReadResult(summary_text=summary_text, recent_turns=recent_turns)
