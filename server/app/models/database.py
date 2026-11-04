from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

CONNECT_TIMEOUT_S = 10


def enable_sqlite_foreign_keys(engine: Engine) -> Engine:
    """SQLite ignores FOREIGN KEY clauses (and ON DELETE) unless asked per connection."""

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if not settings.uses_postgres:
        return enable_sqlite_foreign_keys(
            create_engine(settings.database_url, connect_args={"check_same_thread": False}))
    engine = create_engine(
        settings.database_url,
        # Supabase's pooler drops idle connections; re-check before reuse.
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
    )
    # Models declare no schema; on Postgres they live in settings.db_schema,
    # away from the legacy tables in public.
    return engine.execution_options(schema_translate_map={None: settings.db_schema})


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_connection() -> None:
    """Raise if the database cannot be reached."""
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
