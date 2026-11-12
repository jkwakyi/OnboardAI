"""The migration is the setup step, and it matches the models (ON-11).

"Tables are created by a repeatable setup step" is an acceptance criterion,
so the step itself is tested: it runs from empty, it produces exactly the
schema the models declare, and it reverses.

The drift check is the valuable one. Nothing stops someone adding a column
to `models.py` and forgetting to generate a migration; then the tests pass
on a database built by `create_all` while the real database, built by
`alembic upgrade`, is missing the column. This runs the migration and
compares the result against the models.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db import Base

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
VERSIONS_DIR = BACKEND_ROOT / "migrations" / "versions"


def _config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    """A file database, because Alembic opens its own connections."""
    return f"sqlite+pysqlite:///{(tmp_path / 'main.db').as_posix()}"


def test_the_migration_runs_from_an_empty_database(sqlite_url):
    command.upgrade(_config(sqlite_url), "head")

    tables = set(inspect(create_engine(sqlite_url)).get_table_names())

    assert "alembic_version" in tables
    assert set(Base.metadata.tables) <= tables


def test_the_migration_builds_exactly_what_the_models_declare(sqlite_url):
    """Catches a model changed without a matching migration."""
    command.upgrade(_config(sqlite_url), "head")
    inspector = inspect(create_engine(sqlite_url))

    migrated = {
        name: {column["name"] for column in inspector.get_columns(name)}
        for name in inspector.get_table_names()
        if name != "alembic_version"
    }
    declared = {
        name: {column.name for column in table.columns}
        for name, table in Base.metadata.tables.items()
    }

    assert migrated == declared


def test_the_migration_reverses(sqlite_url):
    """Without a working downgrade, a bad migration has to be undone by hand."""
    config = _config(sqlite_url)
    command.upgrade(config, "head")

    command.downgrade(config, "base")

    remaining = set(inspect(create_engine(sqlite_url)).get_table_names())
    assert remaining - {"alembic_version"} == set()


def test_the_migration_can_be_applied_twice(sqlite_url):
    """Repeatable: running the setup step again is a no-op, not an error."""
    config = _config(sqlite_url)
    command.upgrade(config, "head")

    command.upgrade(config, "head")


def test_there_is_exactly_one_head(sqlite_url):
    """Two heads mean two people generated a migration from the same parent."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_config(sqlite_url))

    assert len(script.get_heads()) == 1, "branched migration history; merge the heads"


def test_every_revision_can_be_undone():
    """A revision with a stub downgrade is a trap discovered at the worst time."""
    for path in VERSIONS_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        body = source.split("def downgrade()", 1)[1]
        assert "pass" != body.split(":", 1)[1].strip(), f"{path.name} cannot be undone"
