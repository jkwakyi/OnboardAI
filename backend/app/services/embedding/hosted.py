"""The Real Embedding Client: the hosted Embedding API over HTTPS (ON-41).

ON-10 chose the provider - OpenAI `text-embedding-3-small`, 1536
dimensions - and merged the configuration and a one-shot check script. This
is the client the application itself uses.

It speaks the shape that endpoint defines: a POST carrying
`{"input": [...], "model": "..."}` with the key in an `Authorization`
header, answered with a `data` array of `{"index": n, "embedding": [...]}`.
`urllib` rather than a new dependency, and the same transport-injection
seam as `scripts/check_embedding_api.py`, so the whole of this file is
exercised by the test suite without a key and without network access.

Three things here are load-bearing and each has a test of its own:

* **Answers are put back in `index` order.** A client that trusted the
  array order would attach vectors to the wrong sections, and the result
  would not look like a bug - it would look like an assistant that cites
  the wrong paragraph with complete confidence.
* **The width is checked against `EMBEDDING_DIMENSIONS`.** The Vector
  Database collection is built for one width. ChromaDB would reject the
  first wrong vector anyway, but the message is clearer here and this
  catches a model change before anything has been written.
* **The key is redacted from anything raised or logged.** Providers echo
  request bodies back inside error payloads.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

from app.config import Settings, get_settings
from app.services.embedding.provider import EmbeddingError, EmbeddingProvider

logger = logging.getLogger(__name__)

Transport = Callable[[urllib.request.Request, float], bytes]


def redact(text: str, secret: str) -> str:
    """Remove the key from text that is about to be shown.

    Deliberately duplicated from `scripts/check_embedding_api.py` rather
    than shared: that script is a developer tool outside the application
    package, and a three-line guard is cheaper to repeat than an import
    that ties the two together.
    """
    if not secret:
        return text
    return text.replace(secret, "***")


def batched(texts: list[str], size: int) -> Iterator[list[str]]:
    """Walk `texts` in chunks of at most `size`."""
    if size < 1:
        raise ValueError("the batch size must be at least 1")
    for start in range(0, len(texts), size):
        yield texts[start : start + size]


def _is_number(value: Any) -> bool:
    """True for an int or a float, but not for a bool.

    `isinstance(True, int)` is True in Python, so without the second half
    of this a provider answering with a list of booleans would be accepted
    and stored as a vector of ones and zeros.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def read_embeddings(payload: Any, expected: int) -> list[list[float]]:
    """Pull `expected` vectors out of one response, in `index` order.

    Separate from the request so every malformed shape can be tested
    without calling anybody.
    """
    if not isinstance(payload, dict):
        raise EmbeddingError("the response was not a JSON object")

    data = payload.get("data")
    if not isinstance(data, list):
        raise EmbeddingError("the response has no 'data' array")
    if len(data) != expected:
        raise EmbeddingError(
            f"asked for {expected} vectors and got {len(data)}; a partial "
            f"answer cannot be matched back to the sections that were sent"
        )

    byindex: dict[int, list[float]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            raise EmbeddingError("an entry of 'data' is not an object")

        index = entry.get("index")
        if not isinstance(index, int) or isinstance(index, bool):
            raise EmbeddingError("an entry of 'data' has no integer 'index'")
        if not 0 <= index < expected:
            raise EmbeddingError(f"'data' holds index {index}, which was not asked for")
        if index in byindex:
            raise EmbeddingError(f"'data' holds index {index} twice")

        vector = entry.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise EmbeddingError(f"'data[{index}].embedding' is missing or empty")
        if not all(_is_number(number) for number in vector):
            raise EmbeddingError(f"'data[{index}].embedding' holds something that is not a number")

        byindex[index] = [float(number) for number in vector]

    # In the order the provider reported, not the order it happened to send.
    return [byindex[index] for index in range(expected)]


class HostedEmbeddingClient(EmbeddingProvider):
    """Calls the configured Embedding API over HTTPS.

    `send` is injected for the tests. Nothing in the application passes it,
    and the real `urlopen` is used.
    """

    def __init__(self, settings: Settings | None = None, send: Transport | None = None) -> None:
        self._settings = settings or get_settings()
        self._send = send if send is not None else _send

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        settings = self._settings
        try:
            key = settings.require_embedding_api_key()
        except RuntimeError as exc:
            # Nothing to send, so this is not an HTTPS failure. The message
            # already says how to fix it and is passed straight through.
            raise EmbeddingError(str(exc)) from None

        vectors: list[list[float]] = []
        for chunk in batched(texts, settings.embedding_batch_size):
            vectors.extend(self._embed_one_batch(chunk, key))

        self._check_widths(vectors)
        return vectors

    # --- one request ----------------------------------------------------

    def _embed_one_batch(self, texts: list[str], key: str) -> list[list[float]]:
        request = self._build_request(texts, key)
        try:
            raw = self._send(request, self._settings.embedding_timeout_seconds)
        except urllib.error.HTTPError as exc:
            raise EmbeddingError(self._describe(exc, key)) from None
        except urllib.error.URLError as exc:
            raise EmbeddingError(f"could not reach the Embedding API: {exc.reason}") from None
        except TimeoutError:
            raise EmbeddingError(
                f"the Embedding API did not answer within "
                f"{self._settings.embedding_timeout_seconds} seconds"
            ) from None

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EmbeddingError(
                f"the Embedding API sent something that is not JSON: {exc}"
            ) from None

        return read_embeddings(payload, expected=len(texts))

    def _build_request(self, texts: list[str], key: str) -> urllib.request.Request:
        body = json.dumps({"input": texts, "model": self._settings.embedding_model}).encode("utf-8")
        return urllib.request.Request(
            self._settings.embedding_api_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def _describe(self, exc: urllib.error.HTTPError, key: str) -> str:
        """A refusal, in the provider's own words and without the key."""
        try:
            detail = exc.read().decode("utf-8", "replace").strip()
        except Exception:  # pragma: no cover - a body that cannot be read twice
            detail = ""
        hints = {
            401: " The key may be wrong or revoked.",
            403: " The key may be wrong or revoked.",
            429: " The account may be out of credit, or the rate limit was hit.",
        }
        message = f"the Embedding API answered {exc.code}.{hints.get(exc.code, '')} {detail}"
        return redact(message.strip(), key)

    def _check_widths(self, vectors: list[list[float]]) -> None:
        expected = self._settings.embedding_dimensions
        for position, vector in enumerate(vectors):
            if len(vector) != expected:
                raise EmbeddingError(
                    f"the Embedding API returned a {len(vector)}-dimension vector "
                    f"for text {position} but EMBEDDING_DIMENSIONS is {expected}. "
                    f"The Vector Database collection is built for one width, so "
                    f"these two have to agree - check EMBEDDING_MODEL."
                )


def _send(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


__all__ = ["HostedEmbeddingClient", "Transport", "batched", "read_embeddings", "redact"]
