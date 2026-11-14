"""The Embedding Client (ON-41).

The two things the application asks of the Embedding Client, and nothing
else:

* `embed_document_sections` - U4. The Document Upload Service has saved the
  original file (U2) and the sections (U3); this turns those sections into
  vectors and stores them in the Vector Database.
* `embed_question` - step 2 of the ask flow. The same client, the same
  model, one vector.

Both go through the same provider, which is the point: a question embedded
by a different model than the sections is a question whose distances mean
nothing, and the symptom would be an assistant that retrieves plausible
rubbish rather than one that visibly fails.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from app.config import Settings
from app.db.models import Section
from app.services.embedding.provider import EmbeddingError, EmbeddingProvider
from app.services.embedding.selection import get_provider
from app.services.embedding.store import remember_sections

logger = logging.getLogger(__name__)


def text_for_embedding(section: Section) -> str:
    """What actually gets embedded for a section.

    The heading goes in front of the body when there is one. A heading is
    the most compressed description a section has - "Parental Leave" over a
    paragraph that never uses either word - and leaving it out throws away
    the best signal in the document. Sections with no heading are embedded
    as they are.
    """
    if section.heading:
        return f"{section.heading}\n\n{section.text}"
    return section.text


def embed_document_sections(
    sections: Sequence[Section],
    provider: EmbeddingProvider | None = None,
    collection: Any | None = None,
    settings: Settings | None = None,
) -> int:
    """Embed `sections` and store the vectors (U4). Returns how many.

    Raises `EmbeddingError` if the provider could not answer. The caller
    decides what that means for the upload; this does not half-finish and
    report success.
    """
    if not sections:
        return 0

    chosen = provider if provider is not None else get_provider(settings)
    vectors = chosen.embed([text_for_embedding(section) for section in sections])

    # The provider interface promises one vector per text, in order, and
    # both implementations here are tested for it. Checked again anyway,
    # because the cost of being wrong is every citation pointing at the
    # wrong paragraph, which no error message would ever reveal.
    if len(vectors) != len(sections):
        raise EmbeddingError(
            f"{chosen.name} returned {len(vectors)} vectors for {len(sections)} "
            f"sections; they cannot be matched up"
        )

    return remember_sections(sections, vectors, collection=collection)


def embed_question(
    question: str,
    provider: EmbeddingProvider | None = None,
    settings: Settings | None = None,
) -> list[float]:
    """Embed one employee question, for the Retrieval Service (step 2)."""
    chosen = provider if provider is not None else get_provider(settings)
    vectors = chosen.embed([question])
    if len(vectors) != 1:
        raise EmbeddingError(f"{chosen.name} returned {len(vectors)} vectors for one question")
    return vectors[0]


__all__ = ["embed_document_sections", "embed_question", "text_for_embedding"]
