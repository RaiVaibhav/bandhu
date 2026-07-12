from datetime import datetime, timedelta, timezone
from uuid import UUID

from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_turns import ConversationTurn
from app.telemetry.langfuse_setup import traced

CONVERSATION_WINDOW = timedelta(hours=2)
CONVERSATION_TURN_LIMIT = 12


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
