import uuid

from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_checkins import UserCheckin
from app.telemetry.langfuse_setup import traced

# "Last 3 check-ins" is by count, not a calendar window — see
# vector-database.md §2, whose own query sketch had a non-functional
# `interval '3 checkins'` placeholder for exactly this reason. Cap value
# (1) is a starting guess, not validated — backend-architecture.md §14.
LOOKBACK_COUNT = 3
HELP_OFFER_CAP = 1


@traced("pipeline.eligibility_gate")
async def check_eligibility(db: AsyncSession, session_id: uuid.UUID) -> bool:
    """Stage 5 — deterministic, not a model decision. Gates offer_suggestion
    and name_thinking_trap only; close_the_loop never counts against this
    cap, and is never gated by it — "care isn't rationed" (§4). Counts
    is_help_offer over the most recent LOOKBACK_COUNT rows in user_checkins
    (structured events), never conversation_turns (raw messages)."""
    result = await db.execute(
        select(UserCheckin.is_help_offer)
        .where(UserCheckin.session_id == session_id)
        .order_by(UserCheckin.created_at.desc())
        .limit(LOOKBACK_COUNT)
    )
    recent_offers = result.scalars().all()
    offer_count = sum(1 for offered in recent_offers if offered)

    eligible = offer_count < HELP_OFFER_CAP

    span = trace.get_current_span()
    span.set_attribute("eligibility_gate.recent_offer_count", offer_count)
    span.set_attribute("eligibility_gate.eligible", eligible)

    return eligible
