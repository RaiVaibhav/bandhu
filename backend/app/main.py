from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.middleware.session import SessionMiddleware
from app.telemetry.langfuse_setup import setup_telemetry

setup_telemetry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Bandhu backend", lifespan=lifespan)
app.add_middleware(SessionMiddleware)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        # Reports whether config is actually loaded, without ever echoing the
        # values themselves back — useful once real keys are in .env, to
        # confirm they're being picked up without printing a secret.
        "database_configured": settings.database_url is not None,
        "anthropic_configured": settings.anthropic_api_key is not None,
        "telemetry_configured": settings.langfuse_public_key is not None,
    }
