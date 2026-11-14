"""Shared test fixtures."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base
from app.main import create_app
from app.services.auth import passwords, tokens
from app.services.embedding import store as embedding_store


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


class FakeCollection:
    """An in-memory stand-in for the ChromaDB collection (ON-41).

    The real one needs a running Vector Database, which a unit test must
    not need. This keeps what was written so a test can assert on it, and
    can be told to fail so the discard path is reachable.

    It deliberately enforces the two rules the real collection enforces and
    that our code could otherwise break silently: ids are strings, and
    every vector in a collection has the same width.
    """

    def __init__(self) -> None:
        self.rows: dict[str, tuple[list[float], dict[str, Any]]] = {}
        self.upsert_calls: list[int] = []
        self.documents_seen: list[Any] = []
        self.fail_with: Exception | None = None
        self.width: int | None = None

    # --- the parts of the ChromaDB API our code uses --------------------

    def upsert(self, ids, embeddings, metadatas, documents=None) -> None:
        # Recorded, not used: the Vector Database is meant to hold vectors
        # and ids, with the section text staying in the Main Database as
        # the single approved copy. A test asserts this stays None.
        self.documents_seen.append(documents)
        if self.fail_with is not None:
            raise self.fail_with
        if not (len(ids) == len(embeddings) == len(metadatas)):
            raise AssertionError("ids, embeddings and metadatas must be the same length")
        for identifier, vector, metadata in zip(ids, embeddings, metadatas, strict=True):
            if not isinstance(identifier, str):
                raise TypeError(f"ChromaDB ids are strings; got {type(identifier).__name__}")
            if self.width is None:
                self.width = len(vector)
            elif len(vector) != self.width:
                raise ValueError(
                    f"Collection expecting embedding with dimension of {self.width}, "
                    f"got {len(vector)}"
                )
            for key, value in metadata.items():
                if value is None:
                    raise ValueError(f"ChromaDB metadata cannot be null; {key!r} is")
            self.rows[identifier] = (list(vector), dict(metadata))
        self.upsert_calls.append(len(ids))

    def delete(self, where=None, ids=None) -> None:
        if ids is not None:
            for identifier in ids:
                self.rows.pop(identifier, None)
            return
        if where:
            for identifier, (_vector, metadata) in list(self.rows.items()):
                if all(metadata.get(key) == value for key, value in where.items()):
                    del self.rows[identifier]

    def count(self) -> int:
        return len(self.rows)

    # --- what the tests read -------------------------------------------

    def metadata_for(self, identifier: str) -> dict[str, Any]:
        return self.rows[identifier][1]

    def vector_for(self, identifier: str) -> list[float]:
        return self.rows[identifier][0]


@pytest.fixture
def collection(monkeypatch) -> FakeCollection:
    """Replace the Vector Database with the fake one, everywhere.

    Patched where `store.py` looked the name up rather than where it is
    defined, because `from app.vectorstore import get_collection` binds the
    function into this module at import time and patching the original
    would leave that binding pointing at the real one.
    """
    fake = FakeCollection()
    monkeypatch.setattr(embedding_store, "get_collection", lambda: fake)
    return fake


@pytest.fixture
def mock_embedding(monkeypatch) -> None:
    """Embed with the mock provider, at a width small enough to read.

    The hosted client has its own tests and is never reached from here: an
    endpoint test that called the real Embedding API would need a key, cost
    money and fail offline.
    """
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "32")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
