"""ChromaDB client for the Vector Database.

Holds section embeddings. Writing and querying them belongs to the Embedding
Client and Retrieval Service; this module only owns the connection and the
collection.
"""

from functools import lru_cache
from typing import Any

import chromadb

from app.config import get_settings


@lru_cache
def get_client() -> chromadb.api.ClientAPI:
    """Return the ChromaDB HTTP client singleton."""
    settings = get_settings()
    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def get_collection() -> Any:
    """Return the section-embeddings collection, creating it if absent."""
    settings = get_settings()
    return get_client().get_or_create_collection(name=settings.chroma_collection)


def check_connection() -> bool:
    """Return True if the Vector Database answers a heartbeat."""
    get_client().heartbeat()
    return True
