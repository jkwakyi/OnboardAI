"""The application builds and exposes only what the contracts define."""

from fastapi.routing import APIRoute

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
    """The four groups exist so later tickets add endpoints in one agreed place."""
    app = create_app()
    tags = {tag for route in app.routes for tag in getattr(route, "tags", [])}
    assert {"auth", "documents", "chat", "escalations"} <= tags or not tags


def test_openapi_schema_generates(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "OnboardAI"
