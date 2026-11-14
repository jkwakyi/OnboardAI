"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base
from app.main import create_app
from app.services.auth import passwords, tokens


@pytest.fixture(autouse=True, scope="session")
def ignore_the_developers_env_file():
    """The suite reads the process environment and no `.env` from disk.

    `Settings` points `env_file` at the repository's `.env`, which is
    exactly right for running the application and exactly wrong for
    testing it: pydantic-settings reads that file whether or not a test
    cleared the matching variable, so `monkeypatch.delenv` cannot make a
    setting absent and a test for "this is not configured" passes only on
    a machine that happens not to configure it.

    That is not hypothetical. Two tests here assert that seeding refuses to
    run without `SEED_EMPLOYEE_PASSWORD` and `SEED_HR_PASSWORD`. Both
    passed in CI and on a fresh checkout, and both failed the moment
    somebody followed the README's own instruction to put those passwords
    in their `.env` - which is to say they failed for the one person who
    had set the project up as documented, and nowhere else.

    Autouse and session-scoped, because any setting in anybody's `.env` can
    change the behaviour under test, not just those two.
    """
    original = Settings.model_config.get("env_file")
    Settings.model_config["env_file"] = ()
    get_settings.cache_clear()
    yield
    Settings.model_config["env_file"] = original
    get_settings.cache_clear()


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
