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


class StubCollection:
    """A collection that reports the space it is actually in.

    The real one does, and `get_collection` refuses any that is not
    cosine, so a stub without this would be a stub the code under test
    rejects.
    """

    def __init__(self, space: str | None = "cosine") -> None:
        if space is None:
            self.configuration_json: dict = {}
        else:
            self.configuration_json = {"hnsw": {"space": space}, "spann": None}


class StubClient:
    """Records how the collection was asked for."""

    def __init__(self, space: str | None = "cosine") -> None:
        self.calls: list[dict] = []
        self.space = space

    def get_or_create_collection(self, **kwargs):
        self.calls.append(kwargs)
        return StubCollection(self.space)


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


# --- the distance space, which nothing downstream could notice ----------


def test_the_collection_is_asked_for_in_cosine_space(stub):
    """The Retrieval Service scores matches as `1 - distance`.

    That arithmetic is true for cosine and false for everything else.
    ChromaDB's default is `l2`, which ranks unit vectors in the same order
    - so the top five would still be the right five, each carrying a score
    that is simply wrong.
    """
    chroma.get_collection()

    assert stub.calls[0]["metadata"] == {"hnsw:space": "cosine"}


def test_a_collection_that_came_back_in_another_space_is_refused(monkeypatch):
    """Asking for cosine is not the same as getting it.

    `get_or_create_collection` ignores the metadata when the collection
    already exists: a collection created before this check was added is
    handed back in `l2`, with the cosine request silently dropped and no
    error of any kind. This is the only place that difference is visible.
    """
    monkeypatch.setattr(chroma, "get_client", lambda: StubClient(space="l2"))

    with pytest.raises(RuntimeError) as refusal:
        chroma.get_collection()

    assert "'l2'" in str(refusal.value)
    assert "delete_collection" in str(refusal.value)


def test_a_collection_that_will_not_say_which_space_it_is_in_is_refused(monkeypatch):
    """Unknown is not the same as fine.

    If a future ChromaDB reshapes this part of its response, the scores
    stop meaning what the threshold in ON-46 assumes they mean. Failing
    here is a one-line fix found immediately; carrying on is an assistant
    that falls back on good answers and nobody knowing why.
    """
    monkeypatch.setattr(chroma, "get_client", lambda: StubClient(space=None))

    with pytest.raises(RuntimeError) as refusal:
        chroma.get_collection()

    assert "would not say" in str(refusal.value)


def test_the_refusal_names_the_collection_so_it_can_be_found(monkeypatch):
    """Including in the command it hands over.

    The message ends with a `delete_collection` call to paste. A command
    that named any other collection would be a message telling somebody
    to delete the wrong data, which is worse than no message at all.
    """
    monkeypatch.setattr(chroma, "get_client", lambda: StubClient(space="ip"))
    monkeypatch.setenv("CHROMA_COLLECTION", "onboardai_sections_old")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError) as refusal:
            chroma.get_collection()
    finally:
        get_settings.cache_clear()

    assert "onboardai_sections_old" in str(refusal.value)
    assert "delete_collection('onboardai_sections_old')" in str(refusal.value)


def test_the_space_is_read_from_the_collection_not_from_what_we_asked_for():
    assert chroma.configured_space(StubCollection("cosine")) == "cosine"
    assert chroma.configured_space(StubCollection("l2")) == "l2"
    assert chroma.configured_space(StubCollection(None)) is None
    assert chroma.configured_space(object()) is None


def test_the_space_the_code_requires_is_cosine():
    """The literal, so renaming the constant cannot move the requirement."""
    assert chroma.DISTANCE_SPACE == "cosine"
