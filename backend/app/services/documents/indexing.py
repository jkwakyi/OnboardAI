"""Turning a stored document into sections in the Main Database (U3).

Where `extraction.py` knows about text and `storage.py` knows about files,
this knows about rows. It is the step the Documents API calls once the
original file is safely on disk, and the step ON-41 will hang the vectors
off: a section's id is what the Vector Database stores its embedding
under, so these rows have to exist and keep their ids before anything can
be embedded.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Document, Section
from app.services.documents.extraction import (
    UnreadableDocument,
    extract_text,
    split_into_sections,
)

logger = logging.getLogger(__name__)


def index_document(
    session: Session, document: Document, settings: Settings | None = None
) -> list[Section]:
    """Read a stored document, split it, and save its sections.

    Raises `UnreadableDocument` when there is no usable text, which the
    Documents API turns into a refusal: a document nothing can be read from
    is one the assistant would silently never cite, and an HR
    administrator who was told the upload worked would have no way to know
    that.
    """
    settings = settings or get_settings()

    text = extract_text(
        Path(document.stored_path),
        document.content_type,
        max_pages=settings.pdf_max_pages,
        max_characters=settings.extraction_max_characters,
        timeout_seconds=settings.extraction_timeout_seconds,
    )

    sections = split_into_sections(
        text,
        max_characters=settings.section_max_characters,
        min_characters=settings.section_min_characters,
    )
    if not sections:
        raise UnreadableDocument("That document contains no readable text.")

    rows = [
        Section(
            document_id=document.id,
            position=section.position,
            heading=section.heading,
            text=section.text,
        )
        for section in sections
    ]
    session.add_all(rows)
    session.commit()

    logger.info(
        "document %s split into %d sections (%d characters of text)",
        document.id,
        len(rows),
        len(text),
    )
    return rows


__all__ = ["index_document"]
