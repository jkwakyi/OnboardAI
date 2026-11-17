"""The Retrieval Service (ON-43, steps 5 and 6).

The contracts give this component one line: "Has the question turned into
a vector (step 5) and gets the top 5 closest sections from the Vector
Database (step 6)." Everything below is about the three ways that can go
quietly wrong.

**The Vector Database does not hold the text.** ON-41 stores vectors, ids
and a little metadata, and nothing else: the Main Database holds the
approved copy of every section, and two stores holding the same text would
eventually disagree about what a citation says. So retrieval is two
lookups, not one - ChromaDB ranks, PostgreSQL supplies the words - and the
join between them is this module's real work.

**A ranking is destroyed by a database round trip.** `SELECT ... WHERE id
IN (...)` returns rows in whatever order the planner likes, which is not
the order the Vector Database put them in. Handing those rows on as they
arrive would mean the best match is wherever it happens to land, and
nothing anywhere would raise: the employee gets an answer built from five
sections that really were the closest five, ordered by accident. So the
rows are indexed by id and re-emitted in the order ChromaDB gave.

**A vector can outlive its section.** The two stores are written in
separate operations with no transaction across them (TD-28), and
`DELETE /api/documents/{id}` removes rows from both. An id that ranks well
and has no row behind it is dropped here, loudly, because the alternative
is a citation pointing at nothing.

What this returns, and what it does not decide
----------------------------------------------
A list of `RetrievedSection`, best first, each carrying a `score`. It does
*not* decide whether that score is good enough: "the best match is below
the relevance threshold" is the QA Controller's call (ON-46), and this
module returning nothing when it found something would hide the number
that decision is made on. An empty list here means the Vector Database had
nothing to offer, which is a different thing and reads differently in a
log.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import Settings
from app.db.models import Section
from app.services.embedding import EmbeddingProvider, embed_question
from app.vectorstore import get_collection

logger = logging.getLogger(__name__)

# Fixed by the Interface Contracts: "Finds the top 5 matching document
# sections." A constant rather than a setting, for the same reason the LLM
# Gateway's 20 seconds is one - a deployment quietly retrieving twenty
# sections would be running a different design, and the prompt the Gateway
# builds is sized around five.
TOP_K = 5

# What ChromaDB is asked for. `documents` is deliberately absent: nothing
# writes it, and asking for it would return a column of nulls that looks
# like section text to anybody reading the response.
INCLUDE = ["distances", "metadatas"]


@dataclass(frozen=True)
class RetrievedSection:
    """One of the closest sections, with the text to answer from.

    `score` is relevance: 1.0 for a section whose vector points exactly
    where the question does, falling as the angle between them opens. It
    is not clamped at zero. A negative score means the section points away
    from the question - rare, and genuinely irrelevant - and rounding that
    up to zero would hide a real signal from the threshold in ON-46.

    `distance` is what the Vector Database actually reported, kept beside
    the score because a number that has been through a conversion is worth
    being able to check against the one that has not.
    """

    section_id: int
    document_id: int
    document: str
    heading: str | None
    position: int
    text: str
    score: float
    distance: float


def relevance(distance: float) -> float:
    """Turn a cosine distance into a relevance score.

    ChromaDB reports cosine *distance*, which is 0 for identical direction
    and grows to 2 for opposite. A threshold is far easier to reason about
    as "how alike are these" than as "how far apart", and every other
    component talks about relevance, so the flip happens once, here.

    `app.vectorstore.chroma` guarantees the collection really is using
    cosine - see the check there. This function would return plausible
    nonsense for any other space, which is exactly why that check is not
    optional.
    """
    return 1.0 - distance


def _ranked_ids(answer: Any) -> list[tuple[int, float]]:
    """The ids and distances ChromaDB returned, in its order.

    A query returns one list per query vector and there is only ever one
    here, so everything is read out of index 0. An id that is not a number
    cannot belong to a section row; it is skipped with a complaint rather
    than crashing retrieval, because one corrupt row should not stop an
    employee getting an answer from the other four.
    """
    id_lists = answer.get("ids") or []
    if not id_lists:
        return []

    distance_lists = answer.get("distances") or []
    distances = distance_lists[0] if distance_lists else []

    ranked: list[tuple[int, float]] = []
    for identifier, distance in zip(id_lists[0], distances, strict=True):
        try:
            ranked.append((int(identifier), float(distance)))
        except (TypeError, ValueError):
            logger.warning(
                "the Vector Database returned %r, which is not a section id; skipping it",
                identifier,
            )
    return ranked


def _sections_by_id(session: Session, ids: Sequence[int]) -> dict[int, Section]:
    """Load the matching sections and their documents in one query.

    `joinedload` because every result needs its document's filename for
    the citation, and five lazy loads behind five sections is five round
    trips to answer one question.
    """
    if not ids:
        return {}
    rows = session.scalars(
        select(Section).options(joinedload(Section.document)).where(Section.id.in_(ids))
    ).all()
    return {row.id: row for row in rows}


def retrieve(
    question: str,
    session: Session,
    limit: int = TOP_K,
    provider: EmbeddingProvider | None = None,
    collection: Any | None = None,
    settings: Settings | None = None,
) -> list[RetrievedSection]:
    """The closest `limit` sections to `question`, best first.

    Raises `EmbeddingError` if the question could not be embedded. The QA
    Controller turns that into the HR fallback; retrieval does not decide
    what a failure means, and must not return "nothing matched" for
    "nothing was asked", which would be indistinguishable to the caller.
    """
    if not question.strip():
        # Nothing to match. Embedding whitespace would cost a request and
        # return the five sections nearest to the origin of the vector
        # space, which is to say five arbitrary ones presented as answers.
        logger.info("retrieval asked for a blank question; returning nothing")
        return []

    vector = embed_question(question, provider=provider, settings=settings)
    target = collection if collection is not None else get_collection()
    answer = target.query(query_embeddings=[vector], n_results=limit, include=INCLUDE)

    ranked = _ranked_ids(answer)
    sections = _sections_by_id(session, [section_id for section_id, _ in ranked])

    results: list[RetrievedSection] = []
    missing: list[int] = []
    for section_id, distance in ranked:
        section = sections.get(section_id)
        if section is None:
            missing.append(section_id)
            continue
        results.append(
            RetrievedSection(
                section_id=section.id,
                document_id=section.document_id,
                document=section.document.filename,
                heading=section.heading,
                position=section.position,
                text=section.text,
                score=relevance(distance),
                distance=distance,
            )
        )

    if missing:
        # Worth a warning rather than a debug line: it means the two stores
        # have drifted (TD-28), and the fix - re-uploading the document, or
        # clearing the stragglers - needs somebody to know it happened.
        logger.warning(
            "the Vector Database ranked %d section(s) with no row in the Main "
            "Database: %s. A document was probably deleted without its vectors.",
            len(missing),
            missing,
        )

    logger.info(
        "retrieved %d section(s) for a question; best score %.3f",
        len(results),
        results[0].score if results else float("nan"),
    )
    return results


__all__ = ["INCLUDE", "TOP_K", "RetrievedSection", "relevance", "retrieve"]
