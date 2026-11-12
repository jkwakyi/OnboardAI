"""Authenticating, and the two synthetic accounts (ON-36).

The database half of the Auth Service. These run against a throwaway SQLite
database, so the login behaviour is tested without a server and without
PostgreSQL: what is being checked is the service, not the transport.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.models import User
from app.services.auth import (
    SYNTHETIC_SUFFIXES,
    SeedRefused,
    authenticate,
    ensure_account,
    find_user,
    hash_password,
    normalise_email,
    read_token,
    seed,
    seed_accounts_from_settings,
    token_for,
)
from app.services.auth.passwords import ScryptParams

PASSWORD = "a development password"


@pytest.fixture
def employee(auth_env, db_session) -> User:
    ensure_account(
        db_session,
        email="employee@onboardai.example",
        full_name="Alex Rivera",
        role="employee",
        password=PASSWORD,
    )
    return find_user(db_session, "employee@onboardai.example")


# --- authenticating ----------------------------------------------------


def test_the_right_credentials_find_the_user(auth_env, db_session, employee):
    found = authenticate(db_session, "employee@onboardai.example", PASSWORD)

    assert found is not None
    assert found.id == employee.id
    assert found.role == "employee"


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("employee@onboardai.example", "the wrong password"),
        ("employee@onboardai.example", ""),
        ("nobody@onboardai.example", PASSWORD),
        ("", PASSWORD),
    ],
)
def test_anything_else_returns_none(auth_env, db_session, employee, email, password):
    assert authenticate(db_session, email, password) is None


def test_a_wrong_password_and_a_missing_account_look_identical(auth_env, db_session, employee):
    """One return value for both.

    A caller that could tell them apart would eventually say so out loud,
    and then the login form answers questions about who works here.
    """
    assert authenticate(db_session, "employee@onboardai.example", "wrong") is None
    assert authenticate(db_session, "nobody@onboardai.example", PASSWORD) is None


def test_the_unknown_account_path_still_hashes_something(auth_env, db_session, monkeypatch):
    """Otherwise an unknown address returns in microseconds and a known one
    takes a quarter of a second, which is an answer in itself."""
    spent = []
    monkeypatch.setattr(
        "app.services.auth.accounts.spend_verification_time",
        lambda: spent.append(True),
    )

    assert authenticate(db_session, "nobody@onboardai.example", PASSWORD) is None
    assert spent == [True]


def test_the_address_is_matched_whatever_its_case(auth_env, db_session, employee):
    """Every mail provider anybody uses folds case, so logging in must too."""
    assert authenticate(db_session, "EMPLOYEE@OnboardAI.Example", PASSWORD) is not None
    assert authenticate(db_session, "  employee@onboardai.example  ", PASSWORD) is not None


def test_the_plain_password_is_nowhere_in_the_row(auth_env, db_session, employee):
    assert PASSWORD not in employee.password_hash
    assert employee.password_hash.startswith("$scrypt$")


# --- the cost upgrade on login -----------------------------------------


def test_a_login_re_hashes_a_password_stored_at_an_older_cost(auth_env, db_session, employee):
    """The only moment the plain password is in hand is the only moment the
    upgrade can happen."""
    employee.password_hash = hash_password(PASSWORD, params=ScryptParams(n=2, r=1, p=1))
    db_session.commit()
    stale = employee.password_hash

    assert authenticate(db_session, employee.email, PASSWORD) is not None

    reread = db_session.scalars(select(User).where(User.id == employee.id)).one()
    assert reread.password_hash != stale
    assert "n=16," in reread.password_hash
    # And the new hash is a working one, not merely a different one.
    assert authenticate(db_session, employee.email, PASSWORD) is not None


def test_a_login_leaves_a_current_hash_alone(auth_env, db_session, employee):
    before = employee.password_hash

    authenticate(db_session, employee.email, PASSWORD)

    assert employee.password_hash == before


def test_a_failed_upgrade_does_not_fail_the_login(auth_env, db_session, employee, caplog):
    """The password was correct. An out-of-date hash that still verifies it
    is not a reason to refuse somebody."""
    employee.password_hash = hash_password(PASSWORD, params=ScryptParams(n=2, r=1, p=1))
    db_session.commit()

    def refuse():
        raise SQLAlchemyError("the database is having a bad day")

    monkeypatched = db_session.commit
    db_session.commit = refuse
    try:
        with caplog.at_level("WARNING"):
            assert authenticate(db_session, employee.email, PASSWORD) is not None
    finally:
        db_session.commit = monkeypatched

    assert "could not re-hash" in caplog.text


# --- the token that comes out of it ------------------------------------


def test_a_token_for_an_authenticated_user_says_who_they_are(auth_env, db_session, employee):
    claims = read_token(token_for(employee))

    assert claims.user_id == employee.id
    assert claims.email == employee.email
    assert claims.full_name == employee.full_name
    assert claims.role == "employee"


def test_an_hr_administrator_gets_their_own_role_in_the_token(auth_env, db_session):
    ensure_account(
        db_session,
        email="hr@onboardai.example",
        full_name="Jordan Blake",
        role="hr_administrator",
        password=PASSWORD,
    )
    administrator = find_user(db_session, "hr@onboardai.example")

    assert read_token(token_for(administrator)).role == "hr_administrator"


# --- seeding -----------------------------------------------------------


def test_seeding_creates_one_employee_and_one_hr_administrator(auth_env, db_session, monkeypatch):
    monkeypatch.setenv("SEED_EMPLOYEE_PASSWORD", "employee-dev-password")
    monkeypatch.setenv("SEED_HR_PASSWORD", "hr-dev-password")
    get_settings.cache_clear()

    outcomes = seed(db_session, get_settings())

    assert [outcome.role for outcome in outcomes] == ["employee", "hr_administrator"]
    assert all(outcome.created for outcome in outcomes)
    roles = db_session.scalars(select(User.role)).all()
    assert sorted(roles) == ["employee", "hr_administrator"]


def test_both_seeded_accounts_can_log_in(auth_env, db_session, monkeypatch):
    """The acceptance criterion as a teammate experiences it."""
    monkeypatch.setenv("SEED_EMPLOYEE_PASSWORD", "employee-dev-password")
    monkeypatch.setenv("SEED_HR_PASSWORD", "hr-dev-password")
    get_settings.cache_clear()
    seed(db_session, get_settings())

    employee = authenticate(db_session, "employee@onboardai.example", "employee-dev-password")
    administrator = authenticate(db_session, "hr@onboardai.example", "hr-dev-password")

    assert employee is not None and employee.role == "employee"
    assert administrator is not None and administrator.role == "hr_administrator"
    # And not with each other's.
    assert authenticate(db_session, "hr@onboardai.example", "employee-dev-password") is None


def test_seeding_twice_resets_rather_than_failing(auth_env, db_session, monkeypatch):
    """Run again after dropping the database, or after forgetting the
    development password. The email column is unique, so the alternative to
    resetting is an error."""
    monkeypatch.setenv("SEED_EMPLOYEE_PASSWORD", "first-password")
    monkeypatch.setenv("SEED_HR_PASSWORD", "hr-dev-password")
    get_settings.cache_clear()
    seed(db_session, get_settings())

    monkeypatch.setenv("SEED_EMPLOYEE_PASSWORD", "second-password")
    get_settings.cache_clear()
    again = seed(db_session, get_settings())

    assert not any(outcome.created for outcome in again)
    assert len(db_session.scalars(select(User)).all()) == 2
    assert authenticate(db_session, "employee@onboardai.example", "second-password") is not None
    assert authenticate(db_session, "employee@onboardai.example", "first-password") is None


def test_seeding_needs_the_passwords_to_come_from_the_environment(auth_env, monkeypatch):
    """No default in the code, so the only copy of a development password
    is in somebody's own .env."""
    monkeypatch.delenv("SEED_EMPLOYEE_PASSWORD", raising=False)
    monkeypatch.delenv("SEED_HR_PASSWORD", raising=False)
    get_settings.cache_clear()

    with pytest.raises(SeedRefused, match="SEED_EMPLOYEE_PASSWORD and SEED_HR_PASSWORD"):
        seed_accounts_from_settings(get_settings())


def test_seeding_is_refused_in_production(auth_env, db_session, monkeypatch):
    monkeypatch.setenv("SEED_EMPLOYEE_PASSWORD", "employee-dev-password")
    monkeypatch.setenv("SEED_HR_PASSWORD", "hr-dev-password")
    monkeypatch.setenv("ONBOARDAI_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(SeedRefused, match="production"):
        seed(db_session, get_settings())

    assert db_session.scalars(select(User)).all() == []


@pytest.mark.parametrize(
    "address",
    [
        "someone@gmail.com",
        "jkwakyi@gmail.com",
        "hr@onboardai.com",
        "employee@onboardai.example.com.evil.net",
    ],
)
def test_an_address_that_could_reach_a_real_person_is_refused(auth_env, db_session, address):
    """What "no synthetic data" has to mean in practice.

    RFC 2606 and RFC 6761 reserve these suffixes precisely so that an
    example address cannot be delivered anywhere.
    """
    with pytest.raises(SeedRefused, match="reserved for examples"):
        ensure_account(
            db_session,
            email=address,
            full_name="Alex Rivera",
            role="employee",
            password=PASSWORD,
        )

    assert db_session.scalars(select(User)).all() == []


@pytest.mark.parametrize("suffix", SYNTHETIC_SUFFIXES)
def test_every_reserved_suffix_is_accepted(auth_env, db_session, suffix):
    local = "person" if suffix.startswith("@") else "person@host"
    address = f"{local}{suffix}"

    outcome = ensure_account(
        db_session,
        email=address,
        full_name="Alex Rivera",
        role="employee",
        password=PASSWORD,
    )

    assert outcome.created is True
    assert outcome.email == address


def test_the_configured_seed_addresses_are_themselves_synthetic(auth_env, monkeypatch):
    """The defaults in config.py have to pass the rule the seeder enforces,
    or the shipped configuration is one the shipped code refuses."""
    monkeypatch.setenv("SEED_EMPLOYEE_PASSWORD", "employee-dev-password")
    monkeypatch.setenv("SEED_HR_PASSWORD", "hr-dev-password")
    get_settings.cache_clear()

    for account in seed_accounts_from_settings(get_settings()):
        assert any(account.email.endswith(suffix) for suffix in SYNTHETIC_SUFFIXES)


def test_a_role_the_contracts_do_not_define_cannot_be_seeded(auth_env, db_session):
    with pytest.raises(SeedRefused, match="not one of the roles"):
        ensure_account(
            db_session,
            email="someone@onboardai.example",
            full_name="Alex Rivera",
            role="superuser",
            password=PASSWORD,
        )


def test_an_account_with_no_password_cannot_be_seeded(auth_env, db_session):
    with pytest.raises(SeedRefused, match="no password"):
        ensure_account(
            db_session,
            email="someone@onboardai.example",
            full_name="Alex Rivera",
            role="employee",
            password="",
        )


def test_an_outcome_never_carries_the_password(auth_env, db_session):
    outcome = ensure_account(
        db_session,
        email="someone@onboardai.example",
        full_name="Alex Rivera",
        role="employee",
        password=PASSWORD,
    )

    assert PASSWORD not in repr(outcome)
    assert PASSWORD not in outcome.describe()


# --- addresses ---------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("Employee@OnboardAI.Example", "employee@onboardai.example"),
        ("  employee@onboardai.example  ", "employee@onboardai.example"),
        ("employee@onboardai.example", "employee@onboardai.example"),
    ],
)
def test_addresses_are_stored_in_one_spelling(given, expected):
    assert normalise_email(given) == expected


def test_the_same_address_in_two_cases_is_one_account(auth_env, db_session):
    ensure_account(
        db_session,
        email="Person@OnboardAI.Example",
        full_name="Alex Rivera",
        role="employee",
        password=PASSWORD,
    )
    second = ensure_account(
        db_session,
        email="person@onboardai.example",
        full_name="Alex Rivera",
        role="hr_administrator",
        password=PASSWORD,
    )

    assert second.created is False
    assert len(db_session.scalars(select(User)).all()) == 1
