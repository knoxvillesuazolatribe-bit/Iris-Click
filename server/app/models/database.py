from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

CONNECT_TIMEOUT_S = 10


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if not settings.uses_postgres:
        return create_engine(settings.database_url, connect_args={"check_same_thread": False})
    return create_engine(
        settings.database_url,
        # Supabase's pooler drops idle connections; re-check before reuse.
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
    )


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
