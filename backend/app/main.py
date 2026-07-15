import json
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import delete, select

from app.clients.db import SessionLocal, get_db
from app.config import settings
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.middleware.rate_limit import PER_IP_LIMIT, PER_SESSION_LIMIT, limiter
from app.middleware.session import SessionMiddleware
from app.models.content_entries import ContentEntry
from app.models.user_checkins import UserCheckin
from app.models.user_sessions import UserSession
from app.pipeline.orchestrator import run_pipeline, run_pipeline_stream
from app.pipeline.stages.evaluator import evaluate_reply, should_sample
from app.pipeline.stages.generate import generate_reply
from app.pipeline.stages.guardrail_check import check_and_fallback
from app.pipeline.stages.memory_read import read_recent_turns, read_summary
from app.pipeline.stages.memory_write import write_checkin, write_turn
from app.pipeline.stages.orchestrator_judgment import OrchestratorDirective
from app.pipeline.stages.retrieval import RetrievedChunk
from app.telemetry.langfuse_setup import setup_telemetry

logger = logging.getLogger(__name__)

setup_telemetry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Bandhu backend", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SessionMiddleware)
# Added last so it's outermost — needs to wrap every other middleware to
# attach CORS headers even to error responses, and to short-circuit
# preflight OPTIONS requests before anything else runs. Frontend and
# backend are different origins in dev (Vite on 5173/4173, FastAPI on
# 8000) — explicit origins, not "*", since bandhu_sid is a credentialed
# cookie and browsers reject wildcard-origin + credentials together.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        # Reports whether config is actually loaded, without ever echoing the
        # values themselves back — useful once real keys are in .env, to
        # confirm they're being picked up without printing a secret.
        # Plain truthiness, not `is not None`: an empty `KEY=` line in .env
        # parses to `''`, not None — `is not None` would silently report
        # "configured" for a key nobody actually filled in. clients/db.py's
        # own engine-creation gate already treats it the same way.
        "database_configured": bool(settings.database_url),
        "nvidia_configured": bool(settings.nvidia_api_key),
        "telemetry_configured": bool(settings.langfuse_public_key),
    }


class MessageRequest(BaseModel):
    text: str


class MessageResponse(BaseModel):
    response: str
    crisis: bool = False
    helplines: list[dict] = []
    help_offer_type: str | None = None
    suggestion_entry_key: str | None = None


async def _run_evaluator_sample(checkin_id, message_text: str, response_text: str) -> None:
    """Stage 12, fired via BackgroundTasks so it never adds latency to the
    response already sent (backend-architecture.md §3). Opens its own DB
    session rather than reusing the request's — the request's session
    closes as soon as the response is sent, before a background task runs."""
    if SessionLocal is None:
        return
    async with SessionLocal() as db:
        try:
            await evaluate_reply(db, checkin_id, message_text, response_text)
        except Exception:
            logger.exception("Sampled evaluator run failed for checkin_id=%s", checkin_id)


@app.post("/message", response_model=MessageResponse)
@limiter.limit(PER_SESSION_LIMIT)
@limiter.limit(PER_IP_LIMIT, key_func=get_remote_address)
async def post_message(
    request: Request,
    body: MessageRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """The one entry point into the 12-stage pipeline — see
    backend-architecture.md §3's request lifecycle. session_id comes from
    SessionMiddleware (request.state.session_id), already issued/validated
    before this route runs. Voice/image input isn't wired here yet —
    ingest.py raises clearly for those input_modes rather than pretending
    to support them (§1/§14: STT/TTS providers are unresolved)."""
    result = await run_pipeline(db, request.state.session_id, body.text, input_mode="text")

    if result.checkin_id is not None and should_sample():
        background_tasks.add_task(_run_evaluator_sample, result.checkin_id, body.text, result.response_text)

    return MessageResponse(
        response=result.response_text,
        crisis=result.crisis,
        helplines=result.helplines,
        help_offer_type=result.help_offer_type,
        suggestion_entry_key=result.suggestion_entry_key,
    )


def _sse(event: dict) -> str:
    """One Server-Sent Events frame — see MDN's `text/event-stream` format.
    A bare `data:` line (no `event:` field) is enough here since every
    frame already carries its own `"type"` key for the frontend to switch
    on; a distinct SSE `event:` name per type would just duplicate that."""
    return f"data: {json.dumps(event)}\n\n"


@app.post("/message/stream")
@limiter.limit(PER_SESSION_LIMIT)
@limiter.limit(PER_IP_LIMIT, key_func=get_remote_address)
async def post_message_stream(
    request: Request,
    body: MessageRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Streaming twin of POST /message — same 12-stage pipeline
    (orchestrator.py's run_pipeline_stream), but Generate's tokens reach
    the client as they're produced instead of only after the full reply is
    ready, same shape as any chat product's typing effect. The safety
    guarantee that made this feel unsafe to do naively (stage 9's guardrail
    needs the *complete* text before it can be trusted) is preserved by
    running that same check incrementally on the growing buffer rather
    than dropping it — see run_pipeline_stream's own docstring.

    Not built on FastAPI's injected `BackgroundTasks` dependency, since
    whether sampled evaluation should even run isn't known until the
    pipeline's "done" event arrives partway through the generator — this
    builds its own BackgroundTasks object and attaches it to the
    StreamingResponse directly instead."""
    background_tasks = BackgroundTasks()

    async def event_stream():
        async for event in run_pipeline_stream(db, request.state.session_id, body.text, input_mode="text"):
            if event["type"] == "done":
                result = event["result"]
                if result.checkin_id is not None and should_sample():
                    background_tasks.add_task(
                        _run_evaluator_sample, result.checkin_id, body.text, result.response_text
                    )
                yield _sse(
                    {
                        "type": "done",
                        "response": result.response_text,
                        "crisis": result.crisis,
                        "helplines": result.helplines,
                        "help_offer_type": result.help_offer_type,
                        "suggestion_entry_key": result.suggestion_entry_key,
                    }
                )
            else:
                yield _sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream", background=background_tasks)


class ThinkingTrapRequest(BaseModel):
    pattern_key: str


class ThinkingTrapResponse(BaseModel):
    response: str


# thinking_trap_followup's own max_tokens — bigger than the ordinary
# ~60-word cap (generate.py's MAX_TOKENS=150) since this is the one turn
# deliberately allowed to run longer (2-4 sentences plus a real question).
THINKING_TRAP_FOLLOWUP_MAX_TOKENS = 300


@app.post("/thinking-trap", response_model=ThinkingTrapResponse)
async def post_thinking_trap(
    request: Request, body: ThinkingTrapRequest, db: AsyncSession = Depends(get_db)
) -> ThinkingTrapResponse:
    """The person just named their own pattern on the Thinking Trap screen
    (docs/ux-flow.html: "the person names what they're feeling. Whatever
    they pick becomes context for the RAG layer, and the conversation
    continues from there, tailored to that pattern.") — a deterministic
    follow-through, not a fresh discretionary call, so this bypasses
    Classify/Eligibility/Orchestrator (stages 3/5/7) entirely rather than
    re-running the full pipeline on a client-side text hack, the same way
    _handle_special_case bypasses stages 5-8 for a different reason. Real
    content lookup by exact entry_key — never trusts the client for
    anything beyond which key it picked, same posture as every other
    entry_key reference in this codebase (content_entries is the source of
    truth, not the request body)."""
    result = await db.execute(select(ContentEntry).where(ContentEntry.entry_key == body.pattern_key))
    entry = result.scalar_one_or_none()
    if entry is None or entry.category != "thinking-trap":
        return ThinkingTrapResponse(
            response="I'm not sure which pattern you meant — want to try picking again?"
        )

    session_id = request.state.session_id
    recent_turns = await read_recent_turns(db, session_id)
    summary_text = await read_summary(db, session_id)

    message_text = f'I think I might be doing this: "{entry.text}"'
    directive = OrchestratorDirective(tool="thinking_trap_followup", target_entry_key=entry.entry_key)
    chunk = RetrievedChunk(entry.entry_key, entry.text, entry.category, entry.tags)

    response_text = await generate_reply(
        message_text,
        recent_turns,
        summary_text,
        directive,
        [chunk],
        max_tokens=THINKING_TRAP_FOLLOWUP_MAX_TOKENS,
    )
    final_text = await check_and_fallback(response_text, message_text, recent_turns, summary_text)

    await write_turn(db, session_id, message_text, final_text)
    await write_checkin(
        db,
        session_id,
        mood_tag=None,
        theme="thinking-trap",
        suggestion_entry_key=entry.entry_key,
        # Not a fresh offer — the person already opted in on the Thinking
        # Trap screen, so this doesn't count against the eligibility gate's
        # offer-frequency cap the way a genuine offer_suggestion would.
        is_help_offer=False,
        input_mode="text",
    )

    return ThinkingTrapResponse(response=final_text)


class ConversationTurnOut(BaseModel):
    role: str
    content: str


class ConversationResponse(BaseModel):
    turns: list[ConversationTurnOut]


@app.get("/conversation", response_model=ConversationResponse)
async def get_conversation(request: Request, db: AsyncSession = Depends(get_db)) -> ConversationResponse:
    """Rehydrates Response.tsx's chat thread on load — a page refresh (or
    any fresh mount of that screen) previously lost everything past the
    first exchange, since the conversation only ever lived in React state,
    never fetched back from what the backend already persists. Reuses
    memory_read's own windowed query (same 2h/12-turn bound Generate itself
    sees) rather than a separate unbounded history query — what the person
    sees on screen should match what Bandhu actually remembers, not exceed
    it and imply continuity that isn't really there."""
    turns = await read_recent_turns(db, request.state.session_id)
    return ConversationResponse(turns=[ConversationTurnOut(**t) for t in turns])


class BreatheResponse(BaseModel):
    intro_text: str


# Fixed opening line, not retrieved — see backend-architecture.md §13: "no
# message, no mood tag, no LLM call needed, because the person already said
# what they want by tapping the button." The breathing pattern itself
# (frontend/src/routes/Breathing.tsx) is a generic, universally-taught
# pacing exercise (box breathing), not sourced clinical content, so there's
# no vetted-knowledge-base entry it could reference — see
# knowledge-base/vetted/grounding-and-psychoeducation.md's own "What's
# deliberately not here" note: mhGAP explicitly excludes breathing scripts.
BREATHE_INTRO_TEXT = "Let's breathe together for a bit. Stay as long as you need."


@app.post("/breathe", response_model=BreatheResponse)
async def post_breathe(request: Request, db: AsyncSession = Depends(get_db)) -> BreatheResponse:
    """Tapping "Breathe" on Home/the suggestion line — a direct ask, not a
    message to classify. Still logs a lightweight user_checkins row
    (theme='breathing') so the Summarizer's bigger picture includes it, same
    reasoning as a Creation (backend-architecture.md §13)."""
    await write_checkin(
        db,
        request.state.session_id,
        mood_tag=None,
        theme="breathing",
        suggestion_entry_key=None,
        is_help_offer=False,
        input_mode="text",
    )
    return BreatheResponse(intro_text=BREATHE_INTRO_TEXT)


class CheckinSummary(BaseModel):
    date: str
    mood_tag: str | None
    theme: str | None


class LookingBackResponse(BaseModel):
    summary_text: str | None
    checkins: list[CheckinSummary]


@app.get("/looking-back", response_model=LookingBackResponse)
async def get_looking_back(request: Request, db: AsyncSession = Depends(get_db)) -> LookingBackResponse:
    """Backs the Looking Back screen (ux-flow.html: "a summary of the week,
    first... then the daily timeline underneath as supporting detail").
    summary_text is the Summarizer's (stage 11) rolling narrative — None on
    a session with no nightly run yet, same cold-start case Generate/
    Orchestrator already treat as "no prior context." The timeline is the
    raw per-checkin facts, most recent first, entirely separate from that
    narrative — this endpoint doesn't synthesize anything itself."""
    summary_text = await read_summary(db, request.state.session_id)

    result = await db.execute(
        select(UserCheckin)
        .where(UserCheckin.session_id == request.state.session_id)
        .order_by(UserCheckin.created_at.desc())
        .limit(30)
    )
    checkins = result.scalars().all()

    return LookingBackResponse(
        summary_text=summary_text,
        checkins=[
            CheckinSummary(date=c.created_at.date().isoformat(), mood_tag=c.mood_tag, theme=c.theme)
            for c in checkins
        ],
    )


@app.delete("/session")
async def delete_session(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Settings' "delete my data" — see ux-flow.html: "Language toggle,
    delete my data... plain language, not buried in a menu tree." Deleting
    the user_sessions row cascades to every table that references it
    (conversation_turns, user_checkins, user_memory_summary, evaluator_scores
    transitively) — same single-DELETE mechanism jobs/cleanup.py's 14-day
    retention job already relies on, just triggered on request instead of by
    age. The session cookie itself is untouched here; SessionMiddleware
    re-issues a fresh session transparently on the next request against the
    now-deleted session_id, the same as any expired session today."""
    await db.execute(delete(UserSession).where(UserSession.session_id == request.state.session_id))
    await db.commit()
    return {"deleted": True}
