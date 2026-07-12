import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.clients.db import SessionLocal
from app.jobs.cleanup import cleanup_expired_sessions

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


def start_scheduler() -> None:
    """Registers the daily cleanup job (§9). One job today; the periodic
    Summarizer (stage 11) will register here the same way once it's built —
    this is the only place APScheduler jobs get wired up, per
    backend-architecture.md's "why APScheduler and not Celery" reasoning."""
    scheduler.add_job(
        _run_cleanup,
        CronTrigger(hour=3, minute=0),
        id="cleanup_expired_sessions",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown()
