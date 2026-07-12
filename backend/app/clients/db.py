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
    create_async_engine(_to_async_url(settings.database_url), echo=False)
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
