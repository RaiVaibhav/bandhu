from datetime import datetime, timezone
from uuid import UUID

from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.llm import SUMMARIZER_MODEL, generate
from app.config import telemetry_config
from app.models.user_checkins import UserCheckin
from app.models.user_memory_summary import UserMemorySummary
from app.models.user_sessions import UserSession
from app.telemetry.langfuse_setup import traced

SUMMARIZER_SYSTEM_PROMPT = """You read a list of structured facts from someone's recent check-ins on a companion mental-health app and write a short rolling narrative capturing the overall pattern — mood trend, recurring themes, what's been offered and whether it helped. A few sentences, never a list, never a direct quote of anything the person said. This narrative is read later by another model deciding how to respond to this person; it is never shown to the person directly, so it can be plain and clinical-adjacent in a way a reply to them never could be.

Respond with ONLY the narrative text — 2 to 4 sentences, no preamble, no markdown, no bullet points."""


def _format_facts(checkins: list[UserCheckin]) -> str:
    lines = []
    for c in checkins:
        parts = [f"mood={c.mood_tag or 'unspecified'}"]
        if c.theme:
            parts.append(f"theme={c.theme}")
        if c.is_help_offer:
            if c.suggestion_helped is True:
                outcome = "helped"
            elif c.suggestion_helped is False:
                outcome = "didn't help"
            else:
                outcome = "outcome unknown"
            parts.append(f"offered a suggestion ({outcome})")
        lines.append(", ".join(parts))
    return "\n".join(f"- {line}" for line in lines)


@traced("pipeline.summarizer")
async def summarize_session(db: AsyncSession, session_id: UUID) -> str | None:
    """Stage 11 — see backend-architecture.md §4. Reads only structured
    user_checkins facts since the last run, never conversation_turns or the
    full text of a creation — "never a transcript" holds at the synthesis
    layer too, not just at storage. Overwrites user_memory_summary (one row
    per session), never appends. Returns the new narrative, or None if
    there was nothing new to summarize since the last run."""
    existing = await db.get(UserMemorySummary, session_id)
    since = (
        datetime.combine(existing.window_end, datetime.min.time(), tzinfo=timezone.utc)
        if existing and existing.window_end
        else None
    )

    query = select(UserCheckin).where(UserCheckin.session_id == session_id)
    if since is not None:
        query = query.where(UserCheckin.created_at > since)
    query = query.order_by(UserCheckin.created_at.asc())

    result = await db.execute(query)
    checkins = list(result.scalars().all())

    span = trace.get_current_span()
    span.set_attribute("summarizer.new_checkin_count", len(checkins))

    if not checkins:
        return None

    facts_text = _format_facts(checkins)
    prior_context = (
        f"\n\nPrior narrative, for continuity — refine or extend it, don't discard it:\n{existing.summary_text}"
        if existing
        else ""
    )

    summary_text = await generate(
        model=SUMMARIZER_MODEL,
        system=SUMMARIZER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Recent check-in facts:\n{facts_text}{prior_context}"}],
        max_tokens=200,
    )

    window_start = existing.window_start if existing and existing.window_start else checkins[0].created_at.date()
    window_end = checkins[-1].created_at.date()

    stmt = (
        pg_insert(UserMemorySummary)
        .values(
            session_id=session_id,
            summary_text=summary_text,
            window_start=window_start,
            window_end=window_end,
        )
        .on_conflict_do_update(
            index_elements=[UserMemorySummary.session_id],
            set_={
                "summary_text": summary_text,
                "window_start": window_start,
                "window_end": window_end,
                "updated_at": datetime.now(timezone.utc),
            },
        )
    )
    await db.execute(stmt)
    await db.commit()

    if telemetry_config.message_content:
        span.set_attribute("summarizer.summary_text", summary_text)

    return summary_text


@traced("jobs.run_summarizer")
async def run_summarizer(db: AsyncSession) -> int:
    """Periodic entry point, wired into APScheduler (jobs/scheduler.py) —
    see backend-architecture.md §14: the exact trigger cadence (nightly
    batch vs. rolling recompute vs. on-demand) isn't finally decided, this
    assumes "nightly batch over every active session", the default the doc
    itself names without locking in. Runs summarize_session for every
    session that still exists — the 14-day cascade already bounds this
    list — skipping sessions with nothing new since their last run."""
    result = await db.execute(select(UserSession.session_id))
    session_ids = result.scalars().all()

    updated = 0
    for session_id in session_ids:
        summary = await summarize_session(db, session_id)
        if summary is not None:
            updated += 1

    trace.get_current_span().set_attribute("summarizer.sessions_updated", updated)
    return updated
