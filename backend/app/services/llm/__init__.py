"""The LLM side of the AI Chatbot Module (ON-44).

Two of the components the architecture diagram names:

* **LLMProvider (interface)** - `generate(prompt)`, the one method
  signature the design fixes.
* **Mock LLM** - "fake answers for Sprint 1", and the default.
* **Real LLM Client** (ON-18) - a local model served by Ollama.

The **LLM Gateway** (ON-45) sits in front of whichever one is selected and
owns the prompt, the 20-second timeout and the JSON check; nothing in this
package knows any of those three.

Choosing a provider is `get_provider()`, which reads `LLM_PROVIDER` and
nothing else. The QA Controller asks for a provider and never learns which
one it got, which is the whole point of the interface.

**The mock stays the default.** ON-18 requires it: CI has no GPU and no
8 GB of weights, and a teammate who has not pulled the model still needs
to run the system. `LLM_PROVIDER=real` is a thing a developer turns on
where the model is, not something that happens to them (TD-01).
"""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.services.llm.mock import MockLLM
from app.services.llm.provider import LLMError, LLMProvider
from app.services.llm.real import RealLLMClient

logger = logging.getLogger(__name__)

# The providers that can be selected, by the name used in LLM_PROVIDER.
PROVIDERS: dict[str, type[LLMProvider]] = {"mock": MockLLM, "real": RealLLMClient}


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
            f"{', '.join(sorted(PROVIDERS))}."
        ) from None

    if name == "mock":
        # Loud, for the same reason EMBEDDING_PROVIDER=mock is loud: the
        # answers it gives are not answers, and a deployment that believes
        # it has a model says so nowhere anybody is looking.
        logger.warning(
            "LLM_PROVIDER=mock: answering with the Mock LLM, which does not "
            "read the handbook. Set LLM_PROVIDER=real for real answers."
        )
        return provider()

    built = provider()
    logger.info("using the %s LLM provider: %s", name, built.name)
    return built


__all__ = [
    "PROVIDERS",
    "LLMError",
    "LLMProvider",
    "MockLLM",
    "RealLLMClient",
    "get_provider",
]
