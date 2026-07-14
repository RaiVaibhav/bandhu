from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy import pool

from alembic import context

from app.clients.db import Base
from app.config import settings

# Import every model module so it registers its table on Base.metadata —
# without this import, autogenerate would see an empty schema.
from app.models import (  # noqa: F401
    content_entries,
    conversation_turns,
    evaluator_scores,
    helplines,
    redirect_templates,
    safety_patterns,
    user_checkins,
    user_memory_summary,
    user_sessions,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Read the real connection string from app settings (.env) instead of
# duplicating it in alembic.ini, which is committed to git. Kept as a plain
# variable rather than passed through config.set_main_option/engine_from_config
# — configparser's interpolation chokes on a literal "%" (e.g. a URL-encoded
# "%40" in a password), which a percent-encoded connection string like
# Supabase's hits in practice.
if settings.database_url:
    url = settings.database_url
    if not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    url = config.get_main_option("sqlalchemy.url")

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
