"""Make one real request to the Embedding API and report what came back.

    python scripts/check_embedding_api.py

This is the check behind ON-10's first acceptance criterion: that the chosen
provider actually answers. Run it once after putting EMBEDDING_API_KEY in
your own .env at the repository root, and whenever the provider, model or
key changes.

It is a developer script, not part of the product. The Embedding Client that
the application uses is ON-41; this only proves the account, key, model and
network path work, and that the vector width matches what the Vector
Database collection will be built for.

Nothing here ever prints the key. The key is read from the environment at
the moment of use, sent in an Authorization header, and redacted out of any
provider error text before it reaches the terminal.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.config import Settings, get_settings

SAMPLE_TEXT = (
    "New employees are enrolled in the medical plan on their first day of employment."
)


@dataclass(frozen=True)
class Outcome:
    """What the check found, in a form that is easy to print and to test."""

    ok: bool
    message: str
    dimensions: int | None = None
    seconds: float | None = None


def redact(text: str, secret: str) -> str:
    """Remove the key from text that is about to be shown."""
    if not secret:
        return text
    return text.replace(secret, "***")


def build_request(settings: Settings, text: str, key: str) -> urllib.request.Request:
    """The POST the provider expects, with the key in the Authorization header."""
    body = json.dumps({"input": text, "model": settings.embedding_model}).encode("utf-8")
    return urllib.request.Request(
        settings.embedding_api_url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )


def read_embedding(payload: dict[str, Any]) -> list[float]:
    """Pull the vector out of the response, failing loudly on a surprise.

    Keeping this separate from the request means the response shape can be
    tested without calling anybody.
    """
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("the response has no 'data' array")
    first = data[0]
    if not isinstance(first, dict):
        raise ValueError("'data[0]' is not an object")
    vector = first.get("embedding")
    if not isinstance(vector, list) or not vector:
        raise ValueError("'data[0].embedding' is missing or empty")
    if not all(isinstance(number, (int, float)) for number in vector):
        raise ValueError("'data[0].embedding' holds something that is not a number")
    return vector


def check(
    settings: Settings,
    text: str = SAMPLE_TEXT,
    send: Callable[[urllib.request.Request, float], bytes] | None = None,
) -> Outcome:
    """Embed one short string and judge the result.

    `send` is injected so the tests can exercise every branch without a key
    and without network access.
    """
    try:
        key = settings.require_embedding_api_key()
    except RuntimeError as exc:
        return Outcome(ok=False, message=str(exc))

    transport = send if send is not None else _send
    request = build_request(settings, text, key)

    started = time.monotonic()
    try:
        raw = transport(request, settings.embedding_timeout_seconds)
    except urllib.error.HTTPError as exc:
        detail = redact(exc.read().decode("utf-8", "replace").strip(), key)
        hint = " The key may be wrong or revoked." if exc.code in (401, 403) else ""
        return Outcome(
            ok=False,
            message=f"{settings.embedding_api_url} answered {exc.code}.{hint} {detail}".strip(),
        )
    except urllib.error.URLError as exc:
        return Outcome(ok=False, message=f"could not reach the provider: {exc.reason}")
    except TimeoutError:
        return Outcome(
            ok=False,
            message=f"no answer within {settings.embedding_timeout_seconds} seconds",
        )
    seconds = time.monotonic() - started

    try:
        vector = read_embedding(json.loads(raw.decode("utf-8")))
    except (ValueError, UnicodeDecodeError) as exc:
        return Outcome(ok=False, message=f"unexpected response: {redact(str(exc), key)}")

    if len(vector) != settings.embedding_dimensions:
        return Outcome(
            ok=False,
            dimensions=len(vector),
            seconds=seconds,
            message=(
                f"the provider returned {len(vector)} dimensions but "
                f"EMBEDDING_DIMENSIONS is {settings.embedding_dimensions}. The "
                f"Vector Database collection is built for one width, so these "
                f"two have to agree."
            ),
        )

    return Outcome(
        ok=True,
        dimensions=len(vector),
        seconds=seconds,
        message="the Embedding API answered with a usable vector",
    )


def _send(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the Embedding API (ON-10)")
    parser.add_argument("--text", default=SAMPLE_TEXT, help="the string to embed")
    args = parser.parse_args(argv)

    settings = get_settings()
    print(f"provider : {settings.embedding_provider}")
    print(f"endpoint : {settings.embedding_api_url}")
    print(f"model    : {settings.embedding_model}")
    print(f"expecting: {settings.embedding_dimensions} dimensions")
    print()

    outcome = check(settings, args.text)

    if outcome.ok:
        print(f"OK  {outcome.message}")
        print(f"    {outcome.dimensions} dimensions in {outcome.seconds:.2f}s")
        return 0

    print(f"FAILED  {outcome.message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
