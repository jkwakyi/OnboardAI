"""The LLM side of the AI Chatbot Module (ON-44).

Two of the components the architecture diagram names:

* **LLMProvider (interface)** - `generate(prompt)`, the one method
  signature the design fixes.
* **Mock LLM** - "fake answers for Sprint 1", and the default.

The **Real LLM Client** is ON-18 and will arrive here as `real.py`,
implementing the same interface. The **LLM Gateway** (ON-45) sits in front
of whichever one is selected and owns the prompt, the 20-second timeout
and the JSON check; nothing in this package knows any of those three.

Choosing a provider is `get_provider()`, which reads `LLM_PROVIDER` and
nothing else. The QA Controller asks for a provider and never learns which
one it got, which is the whole point of the interface.
"""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.services.llm.mock import MockLLM
from app.services.llm.provider import LLMError, LLMProvider

logger = logging.getLogger(__name__)

# The providers that can be selected, by the name used in LLM_PROVIDER.
# "real" is deliberately absent until ON-18 lands: a name that resolves to
# nothing is better than one that resolves to a stub nobody notices.
PROVIDERS: dict[str, type[LLMProvider]] = {"mock": MockLLM}


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """The configured provider.

    An unknown name is an error rather than a silent fall back to the
    mock. Falling back would mean a deployment that believes it is using a
    real model, answers every question with "this came from the Mock LLM",
    and says so nowhere anybody is looking.
    """
    settings = settings or get_settings()
    name = settings.llm_provider.strip().lower()

    try:
        provider = PROVIDERS[name]
    except KeyError:
        raise RuntimeError(
            f"LLM_PROVIDER is {settings.llm_provider!r}, which is not one of: "
            f"{', '.join(sorted(PROVIDERS))}. The real provider arrives with "
            "ON-18; until then the only option is 'mock'."
        ) from None

    logger.info("using the %s LLM provider", name)
    return provider()


__all__ = ["PROVIDERS", "LLMError", "LLMProvider", "MockLLM", "get_provider"]
