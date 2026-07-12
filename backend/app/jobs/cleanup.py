from datetime import datetime, timedelta, timezone

from opentelemetry import trace
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_sessions import UserSession
from app.telemetry.langfuse_setup import traced

RETENTION_WINDOW = timedelta(days=14)


@traced("jobs.cleanup_expired_sessions")
async def cleanup_expired_sessions(db: AsyncSession) -> int:
    """The entire 14-day retention mechanism — see backend-architecture.md
    §9. Deleting a user_sessions row cascades to every table that
    references it (conversation_turns, user_checkins, user_memory_summary,
    and transitively evaluator_scores), so one DELETE here cleans up
    everything, with no per-table cleanup to keep in sync as the schema
    grows. The window resets on activity: last_active_at updates on every
    turn, so this is "2 weeks since this person was last active," not a
    fixed expiry from first visit."""
    cutoff = datetime.now(timezone.utc) - RETENTION_WINDOW
    result = await db.execute(delete(UserSession).where(UserSession.last_active_at < cutoff))
    await db.commit()

    deleted = result.rowcount or 0
    trace.get_current_span().set_attribute("cleanup.sessions_deleted", deleted)
    return deleted
