"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """A test client that does not run startup hooks."""
    return TestClient(create_app())
