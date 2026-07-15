from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Base class every SQLAlchemy model inherits from."""


def _to_async_url(url: str) -> str:
    """Supabase hands out a plain postgresql:// URL; the async engine needs the +psycopg driver named explicitly."""
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


engine = (
    # pool_pre_ping: Supabase's pooler silently closes idle connections
    # server-side well before SQLAlchemy's own pool would recycle them —
    # confirmed directly via a live 500 (psycopg.OperationalError: "server
    # closed the connection unexpectedly") on a plain session-row insert.
    # Without this, a checked-out dead connection fails outright instead of
    # SQLAlchemy transparently discarding and reopening it first.
    create_async_engine(_to_async_url(settings.database_url), echo=False, pool_pre_ping=True, pool_recycle=300)
    if settings.database_url
    else None
)

SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False) if engine else None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields one session per request, closes it after."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with SessionLocal() as session:
        yield session
