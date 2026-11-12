"""The seed script tells the truth and keeps the passwords to itself (ON-36).

The script is a thin wrapper around `app.services.auth.seed`, which is
tested against a real database in `test_auth_accounts.py`. What is tested
here is the part a teammate actually meets: that a missing password or a
production environment produces an explanation and a non-zero exit rather
than a traceback, and that nothing it prints is a password.
"""

import importlib.util
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.config import REPO_ROOT, get_settings
from app.db import Base
from app.db.models import User

SCRIPT_PATH = REPO_ROOT / "scripts" / "seed_accounts.py"
EMPLOYEE_PASSWORD = "employee-dev-password"
HR_PASSWORD = "hr-dev-password"


def _load_script():
    """Import the developer script by path; scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location("seed_accounts", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seed_accounts = _load_script()


@pytest.fixture
def sqlite_sessions(monkeypatch):
    """Point the script's session factory at a throwaway database.

    Yields the connection it is bound to, so a test can look at what the
    script wrote. One connection for the whole test: an in-memory SQLite
    database belongs to its connection and would otherwise vanish between
    the script's session and the assertions.
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    connection = engine.connect()
    factory = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(seed_accounts, "SessionLocal", factory)
    yield connection
    connection.close()


@pytest.fixture
def passwords_set(monkeypatch):
    monkeypatch.setenv("SEED_EMPLOYEE_PASSWORD", EMPLOYEE_PASSWORD)
    monkeypatch.setenv("SEED_HR_PASSWORD", HR_PASSWORD)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_it_creates_both_accounts_and_says_so(auth_env, passwords_set, sqlite_sessions, capsys):
    assert seed_accounts.main([]) == 0

    printed = capsys.readouterr().out
    assert "created employee: employee@onboardai.example" in printed
    assert "created hr_administrator: hr@onboardai.example" in printed

    with Session(sqlite_sessions) as session:
        assert len(session.scalars(select(User)).all()) == 2


def test_it_never_prints_a_password(auth_env, passwords_set, sqlite_sessions, capsys):
    """The one thing a terminal, a screen share and a scrollback all keep."""
    seed_accounts.main([])

    printed = capsys.readouterr()
    assert EMPLOYEE_PASSWORD not in printed.out + printed.err
    assert HR_PASSWORD not in printed.out + printed.err


def test_running_it_again_resets_rather_than_failing(
    auth_env, passwords_set, sqlite_sessions, capsys
):
    seed_accounts.main([])
    capsys.readouterr()

    assert seed_accounts.main([]) == 0
    assert "reset employee" in capsys.readouterr().out


def test_a_missing_password_is_explained_not_raised(auth_env, sqlite_sessions, monkeypatch, capsys):
    monkeypatch.delenv("SEED_EMPLOYEE_PASSWORD", raising=False)
    monkeypatch.delenv("SEED_HR_PASSWORD", raising=False)
    get_settings.cache_clear()

    assert seed_accounts.main([]) == 1

    captured = capsys.readouterr()
    assert "Cannot seed" in captured.err
    assert ".env.example" in captured.err
    assert "SEED_EMPLOYEE_PASSWORD" in captured.err


def test_production_is_refused_with_an_explanation(
    auth_env, passwords_set, sqlite_sessions, monkeypatch, capsys
):
    monkeypatch.setenv("ONBOARDAI_ENV", "production")
    get_settings.cache_clear()

    assert seed_accounts.main([]) == 1
    assert "production" in capsys.readouterr().err


def test_a_database_that_is_not_there_says_which_two_things_to_check(
    auth_env, passwords_set, monkeypatch, capsys
):
    """A teammate who has not run docker compose should read that, not a
    SQLAlchemy traceback."""

    def unreachable():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(seed_accounts, "SessionLocal", unreachable)

    assert seed_accounts.main([]) == 2

    printed = capsys.readouterr().err
    assert "docker compose up -d" in printed
    assert "alembic upgrade head" in printed


def test_list_shows_the_accounts_without_touching_the_database(
    auth_env, passwords_set, monkeypatch, capsys
):
    def refuse():
        raise AssertionError("--list must not open a database session")

    monkeypatch.setattr(seed_accounts, "SessionLocal", refuse)

    assert seed_accounts.main(["--list"]) == 0

    printed = capsys.readouterr().out
    assert "employee@onboardai.example" in printed
    assert "hr@onboardai.example" in printed
    assert EMPLOYEE_PASSWORD not in printed
