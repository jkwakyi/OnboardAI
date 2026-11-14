"""Choosing an embedding provider from configuration (ON-41).

The equivalent for the LLM lives in `app.services.llm.__init__`. This one
is its own module rather than the package `__init__` because `client.py`
needs it, and a package whose `__init__` imports a module that imports the
`__init__` back is a package that fails to import at all.
"""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.services.embedding.hosted import HostedEmbeddingClient
from app.services.embedding.mock import MockEmbedder
from app.services.embedding.provider import EmbeddingProvider

logger = logging.getLogger(__name__)

# The providers that can be selected, by the name used in
# EMBEDDING_PROVIDER. "openai" is the hosted service ON-10 chose and the
# default; "mock" is for CI and for teammates with no key, exactly as
# LLM_PROVIDER=mock is for teammates with no local model.
PROVIDERS: dict[str, type[EmbeddingProvider]] = {
    "openai": HostedEmbeddingClient,
    "mock": MockEmbedder,
}


def get_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """The configured provider.

    An unknown name is an error rather than a silent fall back to the
    mock - the same reasoning as the LLM's selection. A deployment that
    believes it is embedding against OpenAI while actually using the mock
    would retrieve lexically, answer confidently, and say so nowhere
    anybody is looking.
    """
    settings = settings or get_settings()
    name = settings.embedding_provider.strip().lower()

    try:
        provider = PROVIDERS[name]
    except KeyError:
        raise RuntimeError(
            f"EMBEDDING_PROVIDER is {settings.embedding_provider!r}, which is "
            f"not one of: {', '.join(sorted(PROVIDERS))}."
        ) from None

    if name == "mock":
        # Loud, because a mock that goes unnoticed is the failure mode. It
        # produces lexical vectors (TD-27): retrieval will work and the
        # answers it finds will be worse than the real provider's.
        logger.warning(
            "EMBEDDING_PROVIDER=mock: embedding locally with lexical vectors, "
            "not the Embedding API. Retrieval quality is not representative."
        )
    else:
        logger.info("using the %s embedding provider", name)

    return provider(settings)


__all__ = ["PROVIDERS", "get_provider"]
