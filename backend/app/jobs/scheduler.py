import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.clients.db import SessionLocal
from app.jobs.cleanup import cleanup_expired_sessions
from app.pipeline.stages.summarizer import run_summarizer

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_cleanup() -> None:
    if SessionLocal is None:
        # DATABASE_URL isn't configured yet — nothing to clean up, and no
        # session to open. Same graceful-degradation posture as db.py and
        # langfuse_setup.py: the job is still registered and fires on
        # schedule, it just has nothing to do until real credentials exist.
        logger.info("DATABASE_URL not configured — skipping scheduled cleanup run.")
        return
    async with SessionLocal() as db:
        deleted = await cleanup_expired_sessions(db)
        logger.info("Cleanup job: deleted %d expired session(s).", deleted)


async def _run_summarizer() -> None:
    """Nightly batch, per backend-architecture.md §14's own stated default —
    not a finally-decided cadence, see summarizer.py's docstring."""
    if SessionLocal is None:
        logger.info("DATABASE_URL not configured — skipping scheduled summarizer run.")
        return
    async with SessionLocal() as db:
        updated = await run_summarizer(db)
        logger.info("Summarizer job: updated %d session summary/summaries.", updated)


def start_scheduler() -> None:
    """Registers the daily cleanup job (§9) and the periodic Summarizer
    (stage 11) — the only place APScheduler jobs get wired up, per
    backend-architecture.md's "why APScheduler and not Celery" reasoning.
    Runs after cleanup (4am vs. cleanup's 3am) so a session that's about to
    expire isn't summarized on its way out for no reason — not a hard
    dependency, just avoids wasted LLM calls."""
    scheduler.add_job(
        _run_cleanup,
        CronTrigger(hour=3, minute=0),
        id="cleanup_expired_sessions",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_summarizer,
        CronTrigger(hour=4, minute=0),
        id="run_summarizer",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown()
