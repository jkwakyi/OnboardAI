"""ChromaDB client for the Vector Database.

Holds section embeddings. Writing and querying them belongs to the Embedding
Client and Retrieval Service; this module only owns the connection and the
collection - and the two properties of that collection which, if they were
wrong, nothing downstream would notice.
"""

from functools import lru_cache
from typing import Any

import chromadb

from app.config import get_settings

# How the Vector Database measures "close". Cosine, because the Retrieval
# Service (ON-43) reports relevance as `1 - distance` and that arithmetic
# is only true for this space.
#
# ChromaDB's default is `l2`, which is squared Euclidean distance: it ranks
# unit vectors in the same order as cosine, so the top 5 would still be the
# right top 5 - and every score attached to them would be wrong, by an
# amount that varies with the distance. The ranking looking right is what
# makes it dangerous. The relevance threshold in ON-46 is a number compared
# against those scores, so a collection in the wrong space produces an
# assistant that falls back on good matches and answers from bad ones, with
# nothing in any log to say why.
DISTANCE_SPACE = "cosine"


@lru_cache
def get_client() -> chromadb.api.ClientAPI:
    """Return the ChromaDB HTTP client singleton."""
    settings = get_settings()
    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def configured_space(collection: Any) -> str | None:
    """The distance space a collection is actually using, if it will say.

    Read from the collection ChromaDB handed back rather than from what we
    asked for, because those are not the same thing - see
    `_require_cosine`.
    """
    configuration = getattr(collection, "configuration_json", None)
    if not isinstance(configuration, dict):
        return None
    index = configuration.get("hnsw") or configuration.get("spann")
    if not isinstance(index, dict):
        return None
    space = index.get("space")
    return space if isinstance(space, str) else None


def _require_cosine(collection: Any, name: str) -> Any:
    """Refuse a collection that is not measuring distance the way we think.

    `get_or_create_collection` ignores the metadata when the collection
    already exists. It does not merge it, warn about it or fail: a
    collection created by an earlier build - before this module asked for
    cosine - is handed back as an `l2` collection, with the cosine request
    silently dropped. That is the whole reason this check exists, and why
    it reads the collection's own configuration instead of trusting the
    argument above.

    Refusing outright rather than carrying on with a warning, because the
    damage is to the numbers rather than to the run: everything would keep
    working and the scores would all be wrong.
    """
    space = configured_space(collection)
    if space == DISTANCE_SPACE:
        return collection
    found = f"is using {space!r}" if space else "would not say which space it uses"
    raise RuntimeError(
        f"The ChromaDB collection {name!r} {found}, but the Retrieval Service "
        f"scores matches as 1 - distance, which is only true for "
        f"{DISTANCE_SPACE!r}. ChromaDB cannot change the space of an existing "
        f"collection, so this one has to be deleted and the documents "
        f're-uploaded: python -c "import chromadb; '
        f"chromadb.HttpClient(host='HOST', port=PORT).delete_collection('{name}')\""
    )


def get_collection() -> Any:
    """Return the section-embeddings collection, creating it if absent.

    `embedding_function=None` so ChromaDB never embeds anything itself.
    Left at its default it downloads an ONNX model on first use and embeds
    with that - the wrong model, at the wrong width, instead of the
    Embedding API this design is built around, and with nothing in any log
    to say it happened. Everything written here arrives already embedded
    by the Embedding Client (ON-41).
    """
    settings = get_settings()
    collection = get_client().get_or_create_collection(
        name=settings.chroma_collection,
        embedding_function=None,
        metadata={"hnsw:space": DISTANCE_SPACE},
    )
    return _require_cosine(collection, settings.chroma_collection)


def check_connection() -> bool:
    """Return True if the Vector Database answers a heartbeat."""
    get_client().heartbeat()
    return True
