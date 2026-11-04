from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.models.all_models  # noqa: F401
from app.models.base import Base

SERVER_DIR = Path(__file__).resolve().parents[2]


def _alembic(connection) -> Config:
    config = Config(str(SERVER_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def test_upgrade_creates_every_model_table_and_matches_the_models(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}")
    with engine.connect() as connection:
        command.upgrade(_alembic(connection), "head")
        tables = set(inspect(connection).get_table_names())
        assert set(Base.metadata.tables) <= tables
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()
    assert differences == []


def test_downgrade_removes_the_tables(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}")
    with engine.connect() as connection:
        config = _alembic(connection)
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        tables = set(inspect(connection).get_table_names())
    engine.dispose()
    assert tables & set(Base.metadata.tables) == set()
