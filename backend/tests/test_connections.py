"""The backend connects to the Main Database and the Vector Database.

These need the dev stack running:

    docker compose up -d

They are marked `integration` and skipped by default so the unit suite stays
fast and CI can choose when to run them.
"""

import pytest

from app.db import check_connection as check_database
from app.vectorstore import check_connection as check_vectorstore

pytestmark = pytest.mark.integration


def test_main_database_is_reachable():
    assert check_database() is True


def test_vector_database_is_reachable():
    assert check_vectorstore() is True
