"""The Mock Embedder: vectors with no account and no network (ON-41).

Why this exists
---------------
ON-18 fixes the rule for the LLM - keep the Mock LLM selectable by
configuration so CI and teammates without the model can still run the
system - and the Embedding API needs it for exactly the same reason, only
more so. The LLM is a local model somebody might happen to have; the
Embedding API is a paid hosted service with one key, on one machine. Without
a stand-in, CI cannot run the upload flow at all, Brad and Muhammed cannot
run the application they are building, and every retrieval test would need
a billable round trip.

This does not change ON-10's decision. `EMBEDDING_PROVIDER` still defaults
to `openai`, and the mock is reachable only by setting it to `mock`
deliberately.

What it actually computes
-------------------------
The hashing trick: every word is hashed to one of the configured number of
buckets, with a sign, and the resulting vector is scaled to unit length.
That makes it a **lexical** embedding - two texts that share words land
near each other, two that share none do not - which is enough to exercise
retrieval, the top-5 cut and the relevance threshold with results that are
stable and explainable.

It is emphatically **not semantic**. "annual leave" and "paid time off"
share no words and so look unrelated to it, which is the whole thing a real
embedding model is for. Retrieval *quality* cannot be judged against this
provider, only retrieval *mechanics*. Recorded as TD-27.

`blake2b` rather than `hash()`: Python salts string hashing per process, so
`hash()` would give different vectors on every run and a collection written
by one process would be meaningless to the next.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re

from app.config import Settings, get_settings
from app.services.embedding.provider import EmbeddingProvider

logger = logging.getLogger(__name__)

# Words, lowercased. Numbers count: "90 days" and "30 days" should differ.
WORD = re.compile(r"[a-z0-9]+")


def tokenise(text: str) -> list[str]:
    """The words of `text`, lowercased."""
    return WORD.findall(text.lower())


class MockEmbedder(EmbeddingProvider):
    """Deterministic lexical vectors of the configured width."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        width = self._settings.embedding_dimensions
        return [self._vector(text, width) for text in texts]

    def _vector(self, text: str, width: int) -> list[float]:
        vector = [0.0] * width
        for token in tokenise(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % width
            # A sign from a different byte of the same digest, so two words
            # landing in one bucket can cancel instead of always piling up.
            vector[bucket] += 1.0 if digest[4] & 1 else -1.0

        length = math.sqrt(sum(value * value for value in vector))
        if length == 0.0:
            # Either no words at all, or every word cancelled out. A zero
            # vector has no direction, so cosine similarity against it is
            # undefined and ChromaDB would return nonsense distances.
            # One fixed unit vector keeps it a legal, consistently
            # uninteresting point instead.
            unit = [0.0] * width
            unit[0] = 1.0
            return unit

        return [value / length for value in vector]


__all__ = ["MockEmbedder", "tokenise"]
