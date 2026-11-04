from logging.config import fileConfig

from alembic import context
from sqlalchemy import text

import app.models.all_models  # noqa: F401  (registers every table on Base.metadata)
from app.models.base import Base
from app.models.database import get_engine
from app.config import get_settings

config = context.config
if config.config_file_name is not None:
    # Keep loggers that already exist (the app's, when run in-process) working.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    # Supabase's public schema holds the legacy IrisClick tables (two share
    # names with ours). Ours live in settings.db_schema; never touch others.
    if type_ == "table":
        return name in target_metadata.tables
    return True


def _schema() -> str | None:
    """Postgres schema for the tables and alembic_version; None on SQLite."""
    settings = get_settings()
    return settings.db_schema if settings.uses_postgres else None


def run_migrations_offline() -> None:
    # The URL comes from app.config (server/.env), never alembic.ini, so the
    # Supabase password is not duplicated and needs no %-escaping.
    schema = _schema()
    context.configure(
        url=get_settings().database_url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        include_name=include_name,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=schema,
    )
    with context.begin_transaction():
        if schema:
            context.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            context.execute(f'SET search_path TO "{schema}"')
        context.run_migrations()


def _run(connection, schema: str | None) -> None:
    if schema:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        # Unqualified names (and autogenerate's reflection) resolve to our schema.
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
    context.configure(connection=connection, target_metadata=target_metadata,
                      include_name=include_name, version_table_schema=schema)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests hand in their own connection (a temp SQLite file).
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection, None)
        return
    with get_engine().connect() as connection:
        _run(connection, _schema())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
