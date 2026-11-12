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
