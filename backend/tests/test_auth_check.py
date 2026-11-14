"""Auth Check validates the token and role on every request (ON-14).

Eight of the nine endpoints do not exist yet, which is exactly why these
tests mount a stand-in at each of the nine contract paths and drive the
dependency against all of them. The rules arrive before the endpoints do,
so the endpoint tickets inherit a door that is already shut rather than
each having to remember to close it.

The three acceptance criteria are restated at the bottom in the ticket's
own words, so a reader can match them up without taking my word for it.
"""

from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.auth_check import (
    BEARER,
    BOTH_ROLES,
    ENDPOINT_ROLES,
    EXPIRED_TOKEN,
    HR,
    HR_ONLY,
    INVALID_TOKEN,
    MISSING_TOKEN,
    NO_RULE,
    PUBLIC,
    WRONG_ROLE,
    auth_check,
    current_claims,
)
from app.db.session import get_session
from app.main import create_app
from app.services.auth import TokenClaims, ensure_account, issue_token
from tests.test_app import CONTRACT_ENDPOINTS

UNRULED = "/api/an-endpoint-nobody-wrote-a-rule-for"

PROTECTED = sorted(key for key, roles in ENDPOINT_ROLES.items() if roles != PUBLIC)
HR_ENDPOINTS = sorted(key for key, roles in ENDPOINT_ROLES.items() if roles == HR_ONLY)
SHARED_ENDPOINTS = sorted(key for key, roles in ENDPOINT_ROLES.items() if roles == BOTH_ROLES)


def token_for_role(role: str, **overrides) -> str:
    return issue_token(
        overrides.pop("user_id", 7),
        email=overrides.pop("email", "someone@onboardai.example"),
        full_name=overrides.pop("full_name", "Alex Rivera"),
        role=role,
        **overrides,
    )


def bearer(role: str) -> dict[str, str]:
    return {"Authorization": f"{BEARER} {token_for_role(role)}"}


@pytest.fixture
def contract_app(auth_env) -> TestClient:
    """A stand-in at each of the nine contract paths, behind Auth Check.

    Each one answers 200, so any other status in these tests came from the
    door rather than from the room behind it.
    """
    app = FastAPI()
    router = APIRouter(dependencies=[Depends(auth_check)])

    def ok():
        return {"reached": True}

    for method, path in ENDPOINT_ROLES:
        router.add_api_route(path, ok, methods=[method])
    # One route with no row in the table at all.
    router.add_api_route(UNRULED, ok, methods=["GET"])

    app.include_router(router)
    return TestClient(app)


# --- the table matches the contracts -----------------------------------


def test_every_contract_endpoint_has_a_rule():
    """The nine endpoints and the nine rules are the same nine.

    Cross-checked against test_app.py's list rather than a second copy
    written here, so the two cannot drift apart quietly.
    """
    assert set(ENDPOINT_ROLES) == CONTRACT_ENDPOINTS


def test_exactly_one_endpoint_is_public():
    public = [key for key, roles in ENDPOINT_ROLES.items() if roles == PUBLIC]

    assert public == [("POST", "/api/auth/login")]


def test_every_rule_names_a_role_that_exists():
    for endpoint, roles in ENDPOINT_ROLES.items():
        assert roles <= BOTH_ROLES, f"{endpoint} allows a role the system does not define"


# --- no token, bad token -----------------------------------------------


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_a_request_with_no_token_is_rejected(contract_app, method, path):
    response = contract_app.request(method, path)

    assert response.status_code == 401
    assert response.json()["detail"] == MISSING_TOKEN
    assert response.headers["WWW-Authenticate"] == BEARER


@pytest.mark.parametrize(
    "header",
    [
        "",
        "Bearer",
        "Bearer ",
        "Bearer    ",
        "Basic abcdef",
        "Token abcdef",
        "eyJhbGciOiJIUzI1NiJ9.e30.x",
    ],
)
def test_a_token_that_is_not_a_bearer_token_is_rejected(contract_app, header):
    """Including a bare token with no scheme: the header has a grammar and
    guessing at it would mean guessing at other things too."""
    response = contract_app.get("/api/documents", headers={"Authorization": header})

    assert response.status_code == 401
    assert response.json()["detail"] == MISSING_TOKEN


def test_the_scheme_is_matched_case_insensitively(contract_app):
    """RFC 7235 says it is, and a client sending "bearer" is correct."""
    token = token_for_role(HR)

    assert (
        contract_app.get("/api/documents", headers={"Authorization": f"bearer {token}"}).status_code
        == 200
    )


@pytest.mark.parametrize(
    "token",
    ["not-a-token", "a.b.c", "eyJhbGciOiJub25lIn0.eyJzdWIiOiI3In0.", "...."],
)
def test_a_token_that_does_not_verify_is_rejected(contract_app, token):
    response = contract_app.get("/api/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == INVALID_TOKEN


def test_an_expired_token_says_the_session_ended(contract_app, auth_env):
    """A different message from a bad one, because this one is about the
    person rather than about the request: they did nothing wrong."""
    from datetime import UTC, datetime, timedelta

    stale = token_for_role(
        HR, issued_at=datetime.now(UTC) - timedelta(minutes=auth_env.auth_token_ttl_minutes + 1)
    )

    response = contract_app.get("/api/documents", headers={"Authorization": f"Bearer {stale}"})

    assert response.status_code == 401
    assert response.json()["detail"] == EXPIRED_TOKEN


def test_a_rejection_does_not_explain_which_part_of_the_forgery_to_fix(contract_app):
    bad_signature = contract_app.get(
        "/api/documents", headers={"Authorization": "Bearer a.b.c"}
    ).json()
    not_a_token = contract_app.get(
        "/api/documents", headers={"Authorization": "Bearer nonsense"}
    ).json()

    assert bad_signature == not_a_token


# --- roles -------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), HR_ENDPOINTS)
def test_an_hr_administrator_reaches_the_hr_endpoints(contract_app, method, path):
    response = contract_app.request(method, path, headers=bearer(HR))

    assert response.status_code == 200


@pytest.mark.parametrize(("method", "path"), HR_ENDPOINTS)
def test_an_employee_does_not(contract_app, method, path):
    response = contract_app.request(method, path, headers=bearer("employee"))

    assert response.status_code == 403
    assert response.json()["detail"] == WRONG_ROLE


@pytest.mark.parametrize(("method", "path"), SHARED_ENDPOINTS)
@pytest.mark.parametrize("role", ["employee", HR])
def test_both_roles_reach_the_shared_endpoints(contract_app, method, path, role):
    response = contract_app.request(method, path, headers=bearer(role))

    assert response.status_code == 200


def test_a_role_refusal_does_not_ask_for_credentials_again(contract_app):
    """403, not 401: the token was fine. Sending WWW-Authenticate here
    invites a client to throw away a perfectly good session and retry."""
    response = contract_app.post("/api/documents", headers=bearer("employee"))

    assert response.status_code == 403
    assert "WWW-Authenticate" not in response.headers


# --- failing closed ----------------------------------------------------


def test_an_endpoint_with_no_rule_is_refused(contract_app):
    """A route nobody wrote a rule for stops working rather than opening.

    Forgetting a row then costs five minutes of confusion. The other way
    round it costs a hole nobody notices.
    """
    response = contract_app.get(UNRULED, headers=bearer(HR))

    assert response.status_code == 403
    assert response.json()["detail"] == NO_RULE


def test_an_endpoint_with_no_rule_is_refused_even_without_a_token(contract_app):
    assert contract_app.get(UNRULED).status_code == 403


def test_the_rule_is_matched_on_the_route_template_not_the_url(contract_app):
    """`/api/documents/{id}` is one rule, not one per document."""
    for document_id in ("1", "999", "a-slug"):
        refused = contract_app.delete(f"/api/documents/{document_id}", headers=bearer("employee"))
        allowed = contract_app.delete(f"/api/documents/{document_id}", headers=bearer(HR))

        assert refused.status_code == 403
        assert allowed.status_code == 200


# --- who the request belongs to ----------------------------------------


def test_an_endpoint_can_read_who_is_asking(auth_env):
    app = FastAPI()
    router = APIRouter(dependencies=[Depends(auth_check)])

    def who(claims: Annotated[TokenClaims, Depends(current_claims)]):
        return {"id": claims.user_id, "role": claims.role, "email": claims.email}

    router.add_api_route("/api/documents", who, methods=["GET"])
    app.include_router(router)
    client = TestClient(app)

    body = client.get("/api/documents", headers=bearer(HR)).json()

    assert body == {"id": 7, "role": HR, "email": "someone@onboardai.example"}


def test_reading_the_holder_on_a_public_endpoint_is_a_programming_error(auth_env):
    """An endpoint that needs to know who is asking is not a public one,
    and that mismatch is a bug to fix rather than a case to handle."""
    app = FastAPI()
    router = APIRouter(dependencies=[Depends(auth_check)])

    def who(claims: Annotated[TokenClaims, Depends(current_claims)]):
        return {"id": claims.user_id}

    router.add_api_route("/api/auth/login", who, methods=["POST"])
    app.include_router(router)

    with TestClient(app, raise_server_exceptions=True) as client, pytest.raises(RuntimeError):
        client.post("/api/auth/login")


# --- the real application ----------------------------------------------


def test_logging_in_still_needs_no_token(auth_env, db_session):
    """The one endpoint that cannot require one, checked on the real app
    rather than on a stand-in."""
    ensure_account(
        db_session,
        email="employee@onboardai.example",
        full_name="Alex Rivera",
        role="employee",
        password="a development password",
    )
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "employee@onboardai.example", "password": "a development password"},
        )

    assert response.status_code == 200
    assert "token" in response.json()


def test_the_token_the_login_hands_out_opens_the_door(auth_env, db_session):
    """End to end across ON-36, ON-37 and ON-14: log in, then use it."""
    ensure_account(
        db_session,
        email="hr@onboardai.example",
        full_name="Jordan Blake",
        role="hr_administrator",
        password="a development password",
    )
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session

    with TestClient(app) as client:
        token = client.post(
            "/api/auth/login",
            json={"email": "hr@onboardai.example", "password": "a development password"},
        ).json()["token"]

    # GET /api/documents is ON-39's to build, so the token is taken to a
    # stand-in at that path behind the same Auth Check. What is being
    # checked is the handover: a token this application issued, presented
    # the way a client will present it, opens an HR endpoint.
    behind_the_door = FastAPI()
    router = APIRouter(dependencies=[Depends(auth_check)])
    router.add_api_route("/api/documents", lambda: {"reached": True}, methods=["GET"])
    behind_the_door.include_router(router)

    with TestClient(behind_the_door) as client:
        response = client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"reached": True}


def test_the_generated_documentation_offers_somewhere_to_put_a_token(auth_env):
    """The Authorize button on /docs.

    Not decoration: it is how anybody tries these endpoints by hand, and
    an API whose documentation gives you no way to present a token is one
    every reviewer concludes is broken.
    """
    schema = create_app().openapi()

    schemes = schema["components"]["securitySchemes"]
    assert any(
        scheme.get("type") == "http" and scheme.get("scheme") == "bearer"
        for scheme in schemes.values()
    ), f"no bearer scheme in the OpenAPI document: {schemes}"


# --- the acceptance criteria, in the ticket's words --------------------


def test_requests_without_a_valid_token_are_rejected(contract_app):
    for method, path in PROTECTED:
        assert contract_app.request(method, path).status_code == 401
        assert (
            contract_app.request(
                method, path, headers={"Authorization": "Bearer rubbish"}
            ).status_code
            == 401
        )


def test_document_upload_and_the_hr_inbox_are_limited_to_hr(contract_app):
    upload = ("POST", "/api/documents")
    hr_inbox_reply = ("PATCH", "/api/escalations/{id}")

    for method, path in (upload, hr_inbox_reply):
        assert contract_app.request(method, path, headers=bearer("employee")).status_code == 403
        assert contract_app.request(method, path, headers=bearer(HR)).status_code == 200


def test_the_employee_role_can_use_the_chat_page_endpoints(contract_app):
    chat_page = [
        ("POST", "/api/chat/ask"),
        ("POST", "/api/chat/feedback"),
        ("POST", "/api/escalations"),
        ("GET", "/api/escalations"),
    ]

    for method, path in chat_page:
        assert contract_app.request(method, path, headers=bearer("employee")).status_code == 200
