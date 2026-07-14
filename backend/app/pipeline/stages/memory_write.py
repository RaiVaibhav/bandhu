from uuid import UUID

from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_turns import ConversationTurn
from app.models.user_checkins import UserCheckin
from app.telemetry.langfuse_setup import traced


@traced("memory.write")
async def write_turn(db: AsyncSession, session_id: UUID, user_content: str, assistant_content: str) -> None:
    """Stage 10 — after Generate produces a reply, insert both halves of the
    turn under the current session. No trimming here: the 14-day cascade
    from user_sessions already bounds total storage, and memory_read's
    windowed query is what bounds how much of it Claude actually sees on any
    given turn. See backend-architecture.md §2.

    Voice turns already arrive as transcribed text by this point — STT runs
    before stage 1, and raw audio is never persisted (§5) — so this function
    doesn't need to know whether the turn originated as voice."""
    db.add_all(
        [
            ConversationTurn(session_id=session_id, role="user", content=user_content),
            ConversationTurn(session_id=session_id, role="assistant", content=assistant_content),
        ]
    )
    await db.commit()


@traced("memory.write_checkin")
async def write_checkin(
    db: AsyncSession,
    session_id: UUID,
    *,
    mood_tag: str | None,
    theme: str | None,
    suggestion_entry_key: str | None,
    is_help_offer: bool,
    input_mode: str,
) -> UUID:
    """Stage 10's other half — the structured-facts row Eligibility gate
    (stage 5) counts against and Summarizer (stage 11) later reads. One row
    per turn, including the crisis and special-case-redirect branches (see
    pipeline/orchestrator.py) — Eligibility gate's rolling "last 3
    check-ins" count assumes continuous per-turn coverage, not just
    coverage of the reflective path specifically. `is_help_offer` only ever
    true for a genuine offer_suggestion/notice_thinking_trap turn —
    close_the_loop, crisis, and redirect turns all stay false, per the
    "care isn't rationed" design principle (backend-architecture.md §4).
    Returns the new row's id, so a sampled Evaluator call (stage 12) has
    something to key its score on."""
    checkin = UserCheckin(
        session_id=session_id,
        mood_tag=mood_tag,
        theme=theme,
        suggestion_entry_key=suggestion_entry_key,
        is_help_offer=is_help_offer,
        input_mode=input_mode,
    )
    db.add(checkin)
    await db.commit()
    await db.refresh(checkin)

    trace.get_current_span().set_attribute("memory.checkin_is_help_offer", is_help_offer)
    return checkin.id
