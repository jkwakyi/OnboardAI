"""The schema is right on PostgreSQL too (ON-11).

The unit tests build the schema on SQLite, which is quick but is not the
database the system runs on. These check the real one: that the migration
leaves nothing for Alembic to disagree with, and that the constraints the
unit tests rely on are genuinely enforced by PostgreSQL.

They need the dev stack:

    docker compose up -d

Nothing here drops a table or deletes a row that was already there. The
migration is applied, not reversed, and the rows these tests insert are
rolled back.
"""

import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import Base
from tests.test_migrations import BACKEND_ROOT

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(config, "head")
    return create_engine(get_settings().database_url)


@pytest.fixture
def connection(engine):
    """A connection whose work is rolled back, so the dev data is untouched."""
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


def test_the_migrated_database_matches_the_models(engine):
    """An empty diff means nobody has to wonder which one is the truth."""
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, Base.metadata)

    assert differences == []


def test_postgres_enforces_the_two_roles(connection):
    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO users (email, full_name, password_hash, role) "
                "VALUES (:email, 'X', 'hash', 'superuser')"
            ),
            {"email": f"{uuid.uuid4()}@example.com"},
        )


def test_postgres_cascades_a_deleted_document_to_its_sections(connection):
    email = f"{uuid.uuid4()}@example.com"
    user_id = connection.execute(
        text(
            "INSERT INTO users (email, full_name, password_hash, role) "
            "VALUES (:email, 'X', 'hash', 'hr_administrator') RETURNING id"
        ),
        {"email": email},
    ).scalar_one()
    document_id = connection.execute(
        text(
            "INSERT INTO documents (filename, content_type, stored_path, size_bytes, "
            "uploaded_by_id) VALUES ('h.pdf', 'pdf', '/tmp/h.pdf', 1, :user) RETURNING id"
        ),
        {"user": user_id},
    ).scalar_one()
    connection.execute(
        text("INSERT INTO sections (document_id, position, text) VALUES (:doc, 0, 'text')"),
        {"doc": document_id},
    )

    connection.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})

    remaining = connection.execute(
        text("SELECT count(*) FROM sections WHERE document_id = :id"), {"id": document_id}
    ).scalar_one()
    assert remaining == 0


def test_postgres_fills_in_the_timestamps(connection):
    email = f"{uuid.uuid4()}@example.com"
    created = connection.execute(
        text(
            "INSERT INTO users (email, full_name, password_hash, role) "
            "VALUES (:email, 'X', 'hash', 'employee') RETURNING created_at"
        ),
        {"email": email},
    ).scalar_one()

    assert created is not None
    assert created.tzinfo is not None, "timestamps are stored with their time zone"
