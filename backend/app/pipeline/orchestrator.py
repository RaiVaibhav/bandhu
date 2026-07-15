from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from opentelemetry import trace
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_sessions import UserSession
from app.pipeline.stages.classify import ClassifyResult, classify
from app.pipeline.stages.crisis_response import build_crisis_response
from app.pipeline.stages.eligibility_gate import check_eligibility
from app.pipeline.stages.generate import generate_reply, generate_reply_stream
from app.pipeline.stages.guardrail_check import check_and_fallback, check_violations
from app.pipeline.stages.ingest import InputMode, NormalizedMessage, ingest
from app.pipeline.stages.memory_read import read_recent_turns, read_summary
from app.pipeline.stages.memory_write import write_checkin, write_turn
from app.pipeline.stages.orchestrator_judgment import SILENCE, judge
from app.pipeline.stages.redirect import get_redirect
from app.pipeline.stages.retrieval import retrieve
from app.pipeline.stages.safety_gate import SafetyGateResult, check_safety
from app.telemetry.langfuse_setup import traced

# Named distinctly from orchestrator_judgment.py's `judge()` (the stage 7
# LLM-discretion call itself) to avoid confusion — this module is the
# sequencer, per the project layout in backend-architecture.md §11.


class PipelineResult(BaseModel):
    """What a caller (main.py's /message route) actually needs back.
    `checkin_id` is None for the crisis and special-case-redirect branches
    — sampled evaluation (stage 12) only makes sense against a genuinely
    generated reply, not a fixed template, so main.py should only consider
    sampling when this is set."""

    response_text: str
    checkin_id: UUID | None = None
    crisis: bool = False
    helplines: list[dict] = []
    # Surfaces stage 7's directive so the frontend can render the muted
    # quiet-line contextually (ux-flow.html: "at most one small, muted,
    # easy-to-ignore line") and route "want to look at it together?" into
    # Thinking Trap specifically, rather than a generic suggestion.
    help_offer_type: str | None = None
    # Which content_entries row (if any) an "offer_suggestion" turn drew
    # from — e.g. "bt-001" for the breathing invitation. Lets the frontend
    # route a specific suggestion to a real matching screen (Response.tsx
    # routes bt-* to /breathe) instead of only ever getting a generic
    # muted-line experience regardless of what was actually offered.
    suggestion_entry_key: str | None = None


@traced("pipeline.run")
async def run_pipeline(
    db: AsyncSession,
    session_id: UUID,
    raw_text: str,
    *,
    input_mode: InputMode = "text",
) -> PipelineResult:
    """The 12-stage flow (pipeline.html), stages 1-10 synchronous — stages
    11 (Summarizer) and 12 (Evaluator) are async/periodic and deliberately
    not called from here, see jobs/scheduler.py and main.py's
    BackgroundTasks usage. Each stage stays a plain function taking typed
    input and returning typed output (backend-architecture.md §11) — this
    function is just the sequence and the branches, not stage logic itself.

    Implementation note on ordering: the conversation buffer and long-term
    summary are fetched once, right after Safety gate, rather than exactly
    at stage 4's documented position — Safety gate (stage 2) already needs
    the buffer directly per its own spec, and the special-case redirect
    branch (which rejoins the spine at Guardrail, stage 9) needs both
    values ready for Guardrail's own fallback path. Fetching once and
    reusing is the same data every stage would read at its documented
    position, just without a redundant second query."""
    normalized = await ingest(raw_text, input_mode=input_mode)

    recent_turns = await read_recent_turns(db, session_id)
    session = await db.get(UserSession, session_id)
    last_crisis_card_shown_at = session.last_crisis_card_shown_at if session else None

    # 2 — Safety gate
    safety_result = await check_safety(db, normalized.text, recent_turns, last_crisis_card_shown_at, normalized.language)
    if safety_result.triggered:
        return await _handle_crisis(db, session_id, normalized, recent_turns, safety_result)

    summary_text = await read_summary(db, session_id)

    # 3 — Classify
    tags = await classify(normalized.text)
    if tags.special_case is not None:
        return await _handle_special_case(db, session_id, normalized, recent_turns, summary_text, tags)

    # 5 — Eligibility gate
    eligible = await check_eligibility(db, session_id)

    # 6 — Retrieval (runs whenever there's a category tag, regardless of
    # eligibility — "not eligible" only limits what the Orchestrator is
    # allowed to reach for, not whether retrieval prepares content)
    retrieved_chunks = await retrieve(db, normalized.text, [tags.category], normalized.language) if tags.category else []

    # 7 — Orchestrator judgment
    directive = await judge(normalized.text, tags, summary_text, recent_turns, eligible, retrieved_chunks)

    # 8 — Generate
    response_text = await generate_reply(normalized.text, recent_turns, summary_text, directive, retrieved_chunks)

    # 9 — Guardrail check
    final_text = await check_and_fallback(response_text, normalized.text, recent_turns, summary_text)

    # 10 — Memory write → response
    is_help_offer = directive.tool in ("offer_suggestion", "notice_thinking_trap")
    await write_turn(db, session_id, normalized.text, final_text)
    checkin_id = await write_checkin(
        db,
        session_id,
        mood_tag=tags.emotion,
        theme=tags.category,
        suggestion_entry_key=directive.target_entry_key if directive.tool == "offer_suggestion" else None,
        is_help_offer=is_help_offer,
        input_mode=normalized.input_mode,
    )

    return PipelineResult(
        response_text=final_text,
        checkin_id=checkin_id,
        help_offer_type=directive.tool if is_help_offer else None,
        suggestion_entry_key=directive.target_entry_key if directive.tool == "offer_suggestion" else None,
    )


@traced("pipeline.run_stream")
async def run_pipeline_stream(
    db: AsyncSession,
    session_id: UUID,
    raw_text: str,
    *,
    input_mode: InputMode = "text",
) -> AsyncIterator[dict[str, Any]]:
    """Streaming twin of run_pipeline, for main.py's POST /message/stream.
    Stages 1-7 (Safety gate through Orchestrator judgment) run exactly as
    before, synchronously — none of that is shown to the person
    incrementally, so there's nothing to gain by streaming it. Only stage 8
    (Generate) actually streams token deltas to the caller; the crisis and
    special-case branches are fixed, already-fully-known vetted copy, so
    they're yielded as a single delta same as a non-streamed response
    would look, just wrapped in the same event protocol for a uniform
    frontend consumer.

    Yields dicts of one of three shapes:
    - {"type": "delta", "text": str} — append this to what's on screen.
    - {"type": "reset"} — the guardrail tripped mid-stream (stage 9's
      check now runs incrementally, on the accumulating buffer, instead of
      once at the end — see check_violations below); the caller must
      clear whatever partial text it's shown so far. Deltas for the
      fallback acknowledgment-only reply follow immediately after.
    - {"type": "done", "result": PipelineResult} — terminal event, exactly
      the same payload run_pipeline would have returned.

    Guardrail note: because check_violations is a cheap regex/keyword
    check (not a second LLM call), it's safe to re-run on every delta
    without adding meaningful latency — this is what lets real token
    streaming coexist with the existing safety gate instead of forcing a
    choice between them. The rule set itself is unchanged from
    check_and_fallback's own non-streamed use of the same function."""
    normalized = await ingest(raw_text, input_mode=input_mode)

    recent_turns = await read_recent_turns(db, session_id)
    session = await db.get(UserSession, session_id)
    last_crisis_card_shown_at = session.last_crisis_card_shown_at if session else None

    safety_result = await check_safety(db, normalized.text, recent_turns, last_crisis_card_shown_at, normalized.language)
    if safety_result.triggered:
        result = await _handle_crisis(db, session_id, normalized, recent_turns, safety_result)
        yield {"type": "delta", "text": result.response_text}
        yield {"type": "done", "result": result}
        return

    summary_text = await read_summary(db, session_id)

    tags = await classify(normalized.text)
    if tags.special_case is not None:
        result = await _handle_special_case(db, session_id, normalized, recent_turns, summary_text, tags)
        yield {"type": "delta", "text": result.response_text}
        yield {"type": "done", "result": result}
        return

    eligible = await check_eligibility(db, session_id)
    retrieved_chunks = await retrieve(db, normalized.text, [tags.category], normalized.language) if tags.category else []
    directive = await judge(normalized.text, tags, summary_text, recent_turns, eligible, retrieved_chunks)

    buffer_parts: list[str] = []
    violation: str | None = None
    async for delta in generate_reply_stream(normalized.text, recent_turns, summary_text, directive, retrieved_chunks):
        buffer_parts.append(delta)
        violation = check_violations("".join(buffer_parts))
        if violation is not None:
            break
        yield {"type": "delta", "text": delta}

    if violation is not None:
        trace.get_current_span().set_attribute("guardrail.tripped_mid_stream", True)
        trace.get_current_span().set_attribute("guardrail.violation_type", violation)
        final_text = await generate_reply(normalized.text, recent_turns, summary_text, SILENCE, [])
        yield {"type": "reset"}
        yield {"type": "delta", "text": final_text}
    else:
        final_text = "".join(buffer_parts)

    is_help_offer = directive.tool in ("offer_suggestion", "notice_thinking_trap")
    await write_turn(db, session_id, normalized.text, final_text)
    checkin_id = await write_checkin(
        db,
        session_id,
        mood_tag=tags.emotion,
        theme=tags.category,
        suggestion_entry_key=directive.target_entry_key if directive.tool == "offer_suggestion" else None,
        is_help_offer=is_help_offer,
        input_mode=normalized.input_mode,
    )

    result = PipelineResult(
        response_text=final_text,
        checkin_id=checkin_id,
        help_offer_type=directive.tool if is_help_offer else None,
        suggestion_entry_key=directive.target_entry_key if directive.tool == "offer_suggestion" else None,
    )
    yield {"type": "done", "result": result}


async def _handle_crisis(
    db: AsyncSession,
    session_id: UUID,
    normalized: NormalizedMessage,
    recent_turns: list[dict],
    safety_result: SafetyGateResult,
) -> PipelineResult:
    """Triggered → always short-circuits, every time, regardless of
    should_display (pipeline.html: "Bypasses every remaining stage").
    Suppression only changes what's rendered, never whether detection
    stops the normal reflective path — see crisis_response.py. Memory
    write still runs here (unlike stages 3-9, which are genuinely skipped)
    because future hedge-detection depends on this exact turn being in the
    buffer — see backend-architecture.md §2's hedge-corroboration case."""
    crisis = await build_crisis_response(db, safety_result.should_display)

    await write_turn(db, session_id, normalized.text, crisis.response_text)
    await write_checkin(
        db,
        session_id,
        mood_tag=None,
        theme="crisis",
        suggestion_entry_key=None,
        is_help_offer=False,
        input_mode=normalized.input_mode,
    )

    if safety_result.should_display:
        await db.execute(
            update(UserSession)
            .where(UserSession.session_id == session_id)
            .values(last_crisis_card_shown_at=datetime.now(timezone.utc))
        )
        await db.commit()

    trace.get_current_span().set_attribute("pipeline.branch", "crisis")
    return PipelineResult(response_text=crisis.response_text, crisis=True, helplines=crisis.helplines)


async def _handle_special_case(
    db: AsyncSession,
    session_id: UUID,
    normalized: NormalizedMessage,
    recent_turns: list[dict],
    summary_text: str | None,
    tags: ClassifyResult,
) -> PipelineResult:
    """Rejoins the spine at Guardrail check (stage 9), skipping the
    Orchestrator's discretion entirely — pipeline.html's special-case
    redirect branch. Eligibility/Retrieval/Orchestrator-judgment/Generate
    (stages 5-8) never run: the right answer here never depends on any of
    that, it's the same fixed, vetted copy regardless of what else is true
    this turn."""
    redirect_text = await get_redirect(db, tags.special_case)
    final_text = await check_and_fallback(redirect_text, normalized.text, recent_turns, summary_text)

    await write_turn(db, session_id, normalized.text, final_text)
    checkin_id = await write_checkin(
        db,
        session_id,
        mood_tag=None,
        theme=tags.special_case,
        suggestion_entry_key=None,
        is_help_offer=False,
        input_mode=normalized.input_mode,
    )

    trace.get_current_span().set_attribute("pipeline.branch", "special_case_redirect")
    return PipelineResult(response_text=final_text, checkin_id=checkin_id)
