"""Writing section vectors to the Vector Database (ON-41, U4).

`app.vectorstore.chroma` owns the connection and the collection; this owns
what goes into it and what comes back out of it.

What is stored, and what is not
-------------------------------
The embedding, and enough metadata to find the row it came from:
`document_id`, `position` and `heading`. **Not the section text.** The
architecture gives the Vector Database one job - "section embeddings" - and
the Main Database already holds the text as the approved copy. Storing it
in both places would mean two stores that can disagree about what a
citation says, and the one with no transaction around it would be the one
that drifted. The Retrieval Service (ON-43) gets ids and distances from
here and reads the text from the Main Database by id.

A section's id is its id in both stores, as a string, because ChromaDB ids
are strings. `app.db.models.Section` already carries the matching promise:
"Its vector lives in the Vector Database under this row's id, so the id
must stay stable for as long as the section does."

No embedding function
---------------------
The collection is opened with `embedding_function=None` so ChromaDB never
embeds anything itself. Left at its default it would quietly download an
ONNX model and use that instead of the Embedding API the whole design is
built around - producing vectors of the wrong width, from the wrong model,
with nothing in any log to say so.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from app.db.models import Section
from app.vectorstore import get_collection

logger = logging.getLogger(__name__)

# How many vectors go up in one call. ChromaDB enforces a server-side
# maximum - 5461 on the version pinned here - and exceeding it fails the
# whole write. A long handbook can produce a few thousand sections, so this
# stays an order of magnitude inside the limit rather than near it.
MAX_WRITE_BATCH = 500


def section_metadata(section: Section) -> dict[str, Any]:
    """The metadata stored beside a section's vector.

    `heading` is an empty string when the section has none: ChromaDB
    metadata values cannot be null, and a missing key would make the
    metadata shape differ from row to row.
    """
    return {
        "document_id": section.document_id,
        "position": section.position,
        "heading": section.heading or "",
    }


def remember_sections(
    sections: Sequence[Section],
    vectors: Sequence[Sequence[float]],
    collection: Any | None = None,
) -> int:
    """Store one vector per section. Returns how many were written.

    `upsert` rather than `add` so that running this twice for the same
    sections is harmless. A retried upload would otherwise fail on the
    second attempt with a duplicate id, leaving a document whose sections
    exist in the Main Database and whose vectors are half written.
    """
    if len(sections) != len(vectors):
        raise ValueError(
            f"{len(sections)} sections but {len(vectors)} vectors; every section "
            f"needs exactly one, or they cannot be matched up"
        )
    if not sections:
        return 0

    target = collection if collection is not None else get_collection()

    for start in range(0, len(sections), MAX_WRITE_BATCH):
        chunk = sections[start : start + MAX_WRITE_BATCH]
        target.upsert(
            ids=[str(section.id) for section in chunk],
            embeddings=[list(vector) for vector in vectors[start : start + MAX_WRITE_BATCH]],
            metadatas=[section_metadata(section) for section in chunk],
        )

    logger.info("stored %d section vectors in the Vector Database", len(sections))
    return len(sections)


def forget_document(document_id: int, collection: Any | None = None) -> None:
    """Remove every vector belonging to a document.

    `DELETE /api/documents/{id}` removes a document and its sections
    because retrieval must not cite text an HR administrator has withdrawn.
    The vectors are the half of that which retrieval actually searches, so
    leaving them behind would mean a deleted policy still being found -
    and then, with no section row to read the text from, cited as nothing
    at all.
    """
    target = collection if collection is not None else get_collection()
    target.delete(where={"document_id": document_id})
    logger.info("removed the vectors for document %s", document_id)


__all__ = ["MAX_WRITE_BATCH", "forget_document", "remember_sections", "section_metadata"]
