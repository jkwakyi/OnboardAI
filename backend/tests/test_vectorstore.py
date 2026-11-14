"""The Vector Database client (ON-11, extended by ON-41).

`test_connections.py` checks that a real ChromaDB answers, and is marked
`integration` so the unit suite stays fast. This checks *how* the client is
opened, which needs no server at all - and which nothing checked until
fault injection pointed out that every other test in the project uses a
fake collection and so never calls `get_collection` at all.
"""

import pytest

from app.config import get_settings
from app.vectorstore import chroma


class StubClient:
    """Records how the collection was asked for."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get_or_create_collection(self, **kwargs):
        self.calls.append(kwargs)
        return object()


@pytest.fixture
def stub(monkeypatch) -> StubClient:
    client = StubClient()
    monkeypatch.setattr(chroma, "get_client", lambda: client)
    return client


def test_the_collection_brings_no_embedding_function_of_its_own(stub):
    """The one that matters.

    Left to its default, ChromaDB downloads an ONNX sentence-transformer on
    first use and embeds with that - the wrong model, at the wrong width,
    instead of the Embedding API the whole design is built around, and with
    nothing in any log to say it happened. Everything written to this
    collection arrives already embedded by the Embedding Client.
    """
    chroma.get_collection()

    assert stub.calls[0]["embedding_function"] is None


def test_the_collection_name_comes_from_configuration(stub, monkeypatch):
    monkeypatch.setenv("CHROMA_COLLECTION", "a_collection_of_its_own")
    get_settings.cache_clear()
    try:
        chroma.get_collection()
    finally:
        get_settings.cache_clear()

    assert stub.calls[0]["name"] == "a_collection_of_its_own"


def test_the_client_connects_where_it_was_configured_to(monkeypatch):
    seen: dict[str, object] = {}

    def record(host, port):
        seen["host"] = host
        seen["port"] = port
        return StubClient()

    monkeypatch.setattr(chroma.chromadb, "HttpClient", record)
    monkeypatch.setenv("CHROMA_HOST", "vectors.test")
    monkeypatch.setenv("CHROMA_PORT", "9999")
    get_settings.cache_clear()
    # Cached for the life of the process, so a client built by an earlier
    # test would otherwise be handed back and nothing would be recorded.
    chroma.get_client.cache_clear()
    try:
        chroma.get_client()
    finally:
        chroma.get_client.cache_clear()
        get_settings.cache_clear()

    assert seen == {"host": "vectors.test", "port": 9999}
