"""The application builds and exposes only what the contracts define."""

from fastapi.routing import APIRoute

from app.api import auth, chat, documents, escalations
from app.main import create_app

# The nine endpoints in OnboardAI-Interface-Contracts.docx. Nothing else may
# be served under /api. Adding a route here means the contracts changed.
CONTRACT_ENDPOINTS = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/documents"),
    ("GET", "/api/documents"),
    ("DELETE", "/api/documents/{id}"),
    ("POST", "/api/chat/ask"),
    ("POST", "/api/chat/feedback"),
    ("POST", "/api/escalations"),
    ("GET", "/api/escalations"),
    ("PATCH", "/api/escalations/{id}"),
}


def _api_routes(app) -> set[tuple[str, str]]:
    """Every (method, path) the app serves under /api."""
    found = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api"):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                found.add((method, route.path))
    return found


def test_app_builds():
    assert create_app().title == "OnboardAI"


def test_serves_no_endpoint_outside_the_contracts():
    """Guards the rule that endpoints come from the contracts, never invented."""
    extra = _api_routes(create_app()) - CONTRACT_ENDPOINTS
    assert extra == set(), f"endpoints not in the Interface Contracts: {sorted(extra)}"


def test_four_contract_router_groups_are_mounted():
    """The four groups exist so later tickets add endpoints in one agreed place.

    By prefix rather than by tag. Tags live on routes, so a group with no
    endpoints yet contributes none - which is how the earlier version of
    this test passed while all four groups were empty, and why it broke
    the moment one of them had a route.
    """
    groups = {
        "/auth": auth.router,
        "/documents": documents.router,
        "/chat": chat.router,
        "/escalations": escalations.router,
    }

    for prefix, group in groups.items():
        assert group.prefix == prefix

    for method, path in _api_routes(create_app()):
        assert any(
            path == f"/api{prefix}" or path.startswith(f"/api{prefix}/") for prefix in groups
        ), f"{method} {path} belongs to none of the four contract groups"


def test_the_endpoints_that_exist_are_served():
    """The set above is an upper bound; this says it is not empty.

    Without it, an application that mounted nothing at all would pass
    `test_serves_no_endpoint_outside_the_contracts` perfectly.
    """
    served = _api_routes(create_app())

    assert ("POST", "/api/auth/login") in served, "ON-37's endpoint is not mounted"
    assert served <= CONTRACT_ENDPOINTS


def test_openapi_schema_generates(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "OnboardAI"


# --- the browser may call this API (ON-38) -----------------------------


def test_the_frontend_origin_is_allowed(client):
    """Without this every request from the React app is blocked before it
    is sent, and the failure reads as "the server could not be reached".

    Found by driving the real browser, not by a test: every frontend test
    stubs fetch, and the browser is the only thing that enforces the rule.
    """
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_the_port_vite_moves_to_is_allowed_as_well(client):
    """Vite takes 5174 when 5173 is busy, which happens whenever a second
    dev server is already running."""
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"


def test_an_origin_nobody_configured_is_not_allowed(client):
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "https://not-our-app.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_the_authorization_header_may_be_sent(client):
    """The API Client sends the login token with every request. A browser
    will not send that header cross-origin unless it is allowed here."""
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allowed


def test_retry_after_is_readable_by_the_browser(client):
    """Cross-origin, a browser hides every response header except a short
    safelist unless the server says otherwise - so the login page could
    not tell how long the attempt limit has to run.

    Checked on a real response rather than the preflight, because
    Access-Control-Expose-Headers is only sent on the former. An empty body
    is a 422 from request validation, which never reaches the database.
    """
    response = client.post("/api/auth/login", json={}, headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 422
    assert "retry-after" in response.headers.get("access-control-expose-headers", "").lower()


def test_no_origin_is_a_wildcard():
    """A wildcard says any site may call this API with whatever token the
    person holding it has."""
    from app.config import Settings

    assert "*" not in Settings().allowed_origins
