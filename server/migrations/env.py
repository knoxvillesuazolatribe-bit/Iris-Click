from logging.config import fileConfig

from alembic import context

from app.models.base import Base
from app.models.database import get_engine
from app.config import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import every ORM model module here so autogenerate sees its tables.
target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    # Supabase already holds the original IrisClick tables. Without this,
    # autogenerate would emit DROP TABLE for every table no model defines yet.
    if type_ == "table":
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    # The URL comes from app.config (server/.env), never alembic.ini, so the
    # Supabase password is not duplicated and needs no %-escaping.
    context.configure(
        url=get_settings().database_url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        include_name=include_name,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          include_name=include_name)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
