"""POST /api/auth/login (ON-37).

The endpoint through a real HTTP client, against a throwaway database. What
is being checked is the contract as a caller meets it: credentials in, a
login token out, one message for every way it can fail, and a limit on how
often it can be asked.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.auth import CREDENTIALS_REJECTED, login_limiter
from app.db.session import get_session
from app.main import create_app
from app.services.auth import ensure_account, read_token

EMPLOYEE_EMAIL = "employee@onboardai.example"
EMPLOYEE_PASSWORD = "a development password"
HR_EMAIL = "hr@onboardai.example"
HR_PASSWORD = "another development password"

LOGIN = "/api/auth/login"


@pytest.fixture
def api(auth_env, db_session):
    """The application, talking to the test database, with no history."""
    ensure_account(
        db_session,
        email=EMPLOYEE_EMAIL,
        full_name="Alex Rivera",
        role="employee",
        password=EMPLOYEE_PASSWORD,
    )
    ensure_account(
        db_session,
        email=HR_EMAIL,
        full_name="Jordan Blake",
        role="hr_administrator",
        password=HR_PASSWORD,
    )

    application = create_app()
    application.dependency_overrides[get_session] = lambda: db_session
    # The limiter is one object for the process, so a test that fills it
    # would otherwise lock out the next one.
    login_limiter.reset()
    with TestClient(application) as client:
        yield client
    login_limiter.reset()


# --- credentials in, token out -----------------------------------------


def test_logging_in_returns_a_login_token(api):
    response = api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": EMPLOYEE_PASSWORD})

    assert response.status_code == 200
    assert read_token(response.json()["token"]).email == EMPLOYEE_EMAIL


def test_the_token_carries_the_role_that_was_stored(api):
    """Not a role the caller asked for: the one the database holds."""
    for email, password, role in (
        (EMPLOYEE_EMAIL, EMPLOYEE_PASSWORD, "employee"),
        (HR_EMAIL, HR_PASSWORD, "hr_administrator"),
    ):
        token = api.post(LOGIN, json={"email": email, "password": password}).json()["token"]

        assert read_token(token).role == role


def test_the_response_is_the_token_and_nothing_else(api):
    """The contracts say "login token out". A name or a role in the body
    would be a field they do not define - both are in the token already."""
    response = api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": EMPLOYEE_PASSWORD})

    assert set(response.json()) == {"token"}


def test_the_address_is_accepted_however_it_is_typed(api):
    response = api.post(
        LOGIN, json={"email": "  EMPLOYEE@OnboardAI.Example  ", "password": EMPLOYEE_PASSWORD}
    )

    assert response.status_code == 200


# --- the ways it fails -------------------------------------------------


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (EMPLOYEE_EMAIL, "the wrong password"),
        (EMPLOYEE_EMAIL, HR_PASSWORD),
        ("nobody@onboardai.example", EMPLOYEE_PASSWORD),
    ],
)
def test_bad_credentials_are_a_401(api, email, password):
    response = api.post(LOGIN, json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json()["detail"] == CREDENTIALS_REJECTED


def test_every_failure_says_the_same_thing(api):
    """A different message for "no such account" would turn the login form
    into a way to ask who works here."""
    unknown = api.post(LOGIN, json={"email": "nobody@onboardai.example", "password": "x"})
    wrong = api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": "x"})

    assert unknown.status_code == wrong.status_code
    assert unknown.json() == wrong.json()


def test_a_failed_login_returns_no_token(api):
    response = api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": "wrong"})

    assert "token" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"email": EMPLOYEE_EMAIL},
        {"password": EMPLOYEE_PASSWORD},
        {"email": EMPLOYEE_EMAIL, "password": ""},
        {"email": "", "password": EMPLOYEE_PASSWORD},
        {"email": EMPLOYEE_EMAIL, "password": "x" * 2000},
        {"email": "x" * 400, "password": EMPLOYEE_PASSWORD},
        {"email": None, "password": EMPLOYEE_PASSWORD},
        {"email": EMPLOYEE_EMAIL, "password": 12345},
    ],
)
def test_a_malformed_body_is_a_422(api, body):
    """ "The FastAPI layer validates requests" - Interface Contracts."""
    assert api.post(LOGIN, json=body).status_code == 422


def test_an_extra_field_is_refused_rather_than_ignored(api):
    """A client sending a role and getting a 200 back would have every
    reason to think it had been honoured."""
    response = api.post(
        LOGIN,
        json={
            "email": EMPLOYEE_EMAIL,
            "password": EMPLOYEE_PASSWORD,
            "role": "hr_administrator",
        },
    )

    assert response.status_code == 422


def test_a_get_is_not_allowed(api):
    assert api.get(LOGIN).status_code == 405


# --- the attempt limit (TD-20) -----------------------------------------


def test_repeated_failures_are_eventually_refused(api):
    for _ in range(10):
        assert (
            api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": "wrong"}).status_code == 401
        )

    refused = api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": "wrong"})

    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) >= 1


def test_the_right_password_is_refused_too_once_the_limit_is_reached(api):
    """The point of the limit. If the correct password still worked, a
    guesser would simply keep going until they found it."""
    for _ in range(10):
        api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": "wrong"})

    response = api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": EMPLOYEE_PASSWORD})

    assert response.status_code == 429


def test_a_successful_login_clears_the_count(api):
    for _ in range(9):
        api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": "wrong"})

    assert (
        api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": EMPLOYEE_PASSWORD}).status_code
        == 200
    )

    # The ten previous failures are forgotten, so there is a full allowance
    # again rather than one attempt left.
    for _ in range(10):
        assert (
            api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": "wrong"}).status_code == 401
        )


def test_the_limit_counts_a_varied_address_against_the_client_too(api):
    """Otherwise a limit per address is no limit at all: an attacker works
    through a list of addresses and never trips it."""
    for index in range(10):
        api.post(LOGIN, json={"email": f"nobody-{index}@onboardai.example", "password": "wrong"})

    refused = api.post(LOGIN, json={"email": "nobody-99@onboardai.example", "password": "wrong"})

    assert refused.status_code == 429


def test_a_forged_forwarded_header_does_not_buy_a_fresh_allowance(api):
    """Anyone can set X-Forwarded-For, so it is not what the client limit
    is keyed on."""
    for index in range(10):
        api.post(
            LOGIN,
            json={"email": f"nobody-{index}@onboardai.example", "password": "wrong"},
            headers={"X-Forwarded-For": f"10.0.0.{index}"},
        )

    refused = api.post(
        LOGIN,
        json={"email": "nobody-99@onboardai.example", "password": "wrong"},
        headers={"X-Forwarded-For": "10.0.0.99"},
    )

    assert refused.status_code == 429


def test_the_limit_is_checked_before_any_password_is_hashed(api, monkeypatch):
    """A limit applied afterwards still spends a quarter of a second of one
    core on every refused request, which is the other half of what it is
    for."""
    for _ in range(10):
        api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": "wrong"})

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("the request reached the Auth Service past the limit")

    monkeypatch.setattr("app.api.auth.authenticate", must_not_be_called)

    assert api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": "wrong"}).status_code == 429


# --- what gets written down --------------------------------------------


def test_the_password_is_never_logged(api, caplog):
    with caplog.at_level("DEBUG"):
        api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": EMPLOYEE_PASSWORD})
        api.post(LOGIN, json={"email": EMPLOYEE_EMAIL, "password": "a wrong one"})

    assert EMPLOYEE_PASSWORD not in caplog.text
    assert "a wrong one" not in caplog.text


def test_the_token_is_not_logged(api, caplog):
    """A log line with a token in it is a log line that can be signed in
    with."""
    with caplog.at_level("DEBUG"):
        token = api.post(
            LOGIN, json={"email": EMPLOYEE_EMAIL, "password": EMPLOYEE_PASSWORD}
        ).json()["token"]

    assert token not in caplog.text
