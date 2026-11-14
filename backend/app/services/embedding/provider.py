"""The EmbeddingProvider interface (ON-41).

The architecture names an **Embedding API** as an external system and an
**Embedding Client** that calls it. The Interface Contracts fix one method
signature in the whole design - `generate(prompt)` on `LLMProvider` - and
this is not it, so the shape here is ours to choose. It is chosen to match
`LLMProvider` anyway: an abstract base class with one method, so a class
that forgets to implement it fails when somebody tries to build it rather
than later when something asks it for a vector.

One method, taking a list
-------------------------
`embed(texts)` rather than `embed(text)`. A document arrives as many
sections at once (U4), and a provider that could only be asked for one
vector at a time would turn one upload into one HTTPS request per section -
for a long handbook, hundreds of round trips where a handful would do. The
question path (step 2) asks for a list of one, which costs nothing.

The order of the returned vectors matches the order of `texts`, and the
length matches too. Retrieval stores a vector against a section id, so a
provider that quietly reordered its answers would attach every vector to
the wrong section and the system would cite confidently and wrongly. That
guarantee is the provider's to keep, and each implementation here is
tested for it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingError(Exception):
    """A provider could not turn text into vectors.

    One type for every reason - no key, a refusal, a timeout, an
    unreachable host, a reply that made no sense, the wrong vector width -
    so a caller has one thing to catch rather than a list that grows every
    time somebody adds a provider. The message is for a developer reading a
    log, not for an employee: nothing in the answer path shows it.
    """


class EmbeddingProvider(ABC):
    """Something that can turn text into vectors."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per entry of `texts`, in the same order.

        Every vector has the configured width, because the Vector Database
        collection is built for exactly one. Raises `EmbeddingError` if the
        provider could not answer, or answered with something unusable.

        An empty list in means an empty list out and no request at all: a
        document with no sections is a document the caller should not be
        paying a round trip for.
        """

    @property
    def name(self) -> str:
        """Which provider this is, for logs and for the refinement report.

        Nothing in the answer path reads it - it answers questions about
        the system rather than questions from an employee.
        """
        return type(self).__name__


__all__ = ["EmbeddingError", "EmbeddingProvider"]
