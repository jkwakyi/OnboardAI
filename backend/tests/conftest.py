"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base
from app.main import create_app
from app.services.auth import passwords, tokens


@pytest.fixture
def client() -> TestClient:
    """A test client that does not run startup hooks."""
    return TestClient(create_app())


@pytest.fixture
def db_session():
    """A throwaway SQLite database with foreign keys actually enforced.

    SQLite ignores foreign keys unless asked, and a suite that silently
    skipped every cascade and RESTRICT rule would pass no matter what the
    schema said.

    One shared connection, usable from any thread, because the endpoint
    tests go through `TestClient`: FastAPI runs a synchronous endpoint in a
    threadpool, and SQLite objects belong to the thread that made them. The
    default pool would also hand each thread its own connection, and an
    in-memory database belongs to its connection - so the request would
    look at an empty database and the test would be testing nothing.
    """
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def auth_env(monkeypatch):
    """Settings for the auth tests: a fixed signing key and cheap hashing.

    The real scrypt cost is a quarter of a second per hash, which is the
    point of it and is also several minutes across a suite that hashes in
    most of its tests. Turning it down here is safe because every stored
    hash records the parameters it was made with, so nothing in the product
    has to know which cost produced the hash it is checking - and
    `test_auth_passwords.py` asserts the shipped default separately, from a
    clean environment, so this fixture cannot hide a weakened default.

    Everything reads `get_settings()` at the moment of use, so clearing its
    cache is enough to reach every module at once. The two per-process
    caches inside the Auth Service are cleared with it, or a key or decoy
    hash from one test would outlive its settings.
    """
    monkeypatch.setenv("PASSWORD_SCRYPT_N", "16")
    monkeypatch.setenv("PASSWORD_SCRYPT_R", "8")
    monkeypatch.setenv("PASSWORD_SCRYPT_P", "1")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-signing-key-long-enough-to-be-accepted")
    monkeypatch.setenv("ONBOARDAI_ENV", "test")

    def reset():
        get_settings.cache_clear()
        passwords._decoy_hash_for.cache_clear()
        tokens._development_secret.cache_clear()

    reset()
    yield get_settings()
    reset()
