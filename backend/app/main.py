import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.db import SessionLocal, get_db
from app.config import settings
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.middleware.rate_limit import PER_IP_LIMIT, PER_SESSION_LIMIT, limiter
from app.middleware.session import SessionMiddleware
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.stages.evaluator import evaluate_reply, should_sample
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
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
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

    return MessageResponse(response=result.response_text, crisis=result.crisis, helplines=result.helplines)
