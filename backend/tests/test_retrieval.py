"""The Retrieval Service (ON-43, steps 5 and 6).

The component has one job and three ways of doing it wrongly without
failing, so that is what most of these are about:

* the top 5 are found but handed on in the wrong order,
* a vector outlives the section it came from and is cited as nothing,
* the scores are computed against a distance that is not cosine.

The fake collection in `conftest.py` really does rank by cosine distance,
so an ordering test here fails when the ordering is lost rather than
agreeing with whatever order the fake happened to store things in.
"""

from __future__ import annotations

import logging
import math
from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy import event

from app.db.models import Document, Section, User
from app.services.embedding.provider import EmbeddingError, EmbeddingProvider
from app.services.retrieval import TOP_K, RetrievedSection, relevance, retrieve
from app.services.retrieval import service as retrieval

# Three unit vectors in a plane, so "which is closest" is arithmetic a
# reader can check: NORTH and NORTH_EAST are 45 degrees apart, NORTH and
# EAST are perpendicular.
NORTH = [0.0, 1.0]
NORTH_EAST = [math.sqrt(0.5), math.sqrt(0.5)]
EAST = [1.0, 0.0]
SOUTH = [0.0, -1.0]


class FixedProvider(EmbeddingProvider):
    """Embeds every question as the same vector, so a test can aim it."""

    def __init__(self, vector: list[float]) -> None:
        self.vector = vector
        self.asked: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.asked.extend(texts)
        return [list(self.vector) for _ in texts]


class FailingProvider(EmbeddingProvider):
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("the Embedding API answered 503.")


# --- building the two stores -------------------------------------------


def _document(session, filename: str = "handbook.pdf") -> Document:
    owner = session.query(User).first()
    if owner is None:
        owner = User(
            email="hr@example.com",
            full_name="Jordan HR",
            password_hash="scrypt:not-a-real-hash",
            role="hr_administrator",
        )
        session.add(owner)
        session.flush()
    document = Document(
        filename=filename,
        content_type="pdf",
        stored_path=f"backend/storage/documents/{filename}",
        size_bytes=1024,
        uploaded_by=owner,
    )
    session.add(document)
    session.flush()
    return document


def _section(session, document: Document, position: int, text: str, heading=None) -> Section:
    section = Section(document=document, position=position, heading=heading, text=text)
    session.add(section)
    session.flush()
    return section


def _store(collection, section: Section, vector: list[float]) -> None:
    collection.upsert(
        ids=[str(section.id)],
        embeddings=[vector],
        metadatas=[{"document_id": section.document_id, "position": section.position}],
    )


@pytest.fixture
def library(db_session, collection):
    """Three sections whose vectors point in three known directions."""
    document = _document(db_session)
    sections = {
        "north": _section(db_session, document, 0, "Holiday is 20 days.", "Holiday"),
        "north_east": _section(db_session, document, 1, "Sick leave is 10 days.", "Sick Leave"),
        "east": _section(db_session, document, 2, "The office is on Main Street."),
    }
    _store(collection, sections["north"], NORTH)
    _store(collection, sections["north_east"], NORTH_EAST)
    _store(collection, sections["east"], EAST)
    db_session.commit()
    return sections


# --- the distance-to-relevance flip ------------------------------------


def test_an_exact_match_scores_one():
    assert relevance(0.0) == 1.0


def test_a_perpendicular_section_scores_zero():
    """Cosine distance 1.0 is "these have nothing in common"."""
    assert relevance(1.0) == 0.0


def test_an_opposing_section_scores_below_zero():
    """Not clamped.

    ChromaDB's cosine distance runs to 2.0 for vectors pointing opposite
    ways. Rounding that up to zero would tell the threshold in ON-46 that
    an actively wrong match is merely a useless one, and lose the only
    signal that distinguishes them.
    """
    assert relevance(2.0) == -1.0


# --- the ranking, and surviving the trip through PostgreSQL ------------


def test_the_closest_section_comes_first(db_session, collection, library):
    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert [result.section_id for result in results] == [
        library["north"].id,
        library["north_east"].id,
        library["east"].id,
    ]


def test_asking_in_a_different_direction_reorders_the_answer(db_session, collection, library):
    """The same three sections, a different question, a different order.

    Pinning one order only would pass for an implementation that sorted by
    section id, which is also the order they were inserted in.
    """
    results = retrieve(
        "the office", db_session, provider=FixedProvider(EAST), collection=collection
    )

    assert [result.section_id for result in results] == [
        library["east"].id,
        library["north_east"].id,
        library["north"].id,
    ]


def test_the_ranking_is_not_the_order_the_database_returns_rows(db_session, collection, library):
    """The fault this component exists to avoid.

    `SELECT ... WHERE id IN (...)` returns rows in the planner's order,
    which here is ascending id - the exact reverse of the right answer for
    this question. Nothing raises if that order is passed on; the employee
    just gets an answer built from the right five sections ranked by
    accident.
    """
    results = retrieve(
        "the office", db_session, provider=FixedProvider(EAST), collection=collection
    )

    ids = [result.section_id for result in results]
    assert ids != sorted(ids), "the results came back in database order, not in rank order"


def test_the_scores_fall_with_the_angle(db_session, collection, library):
    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert [round(result.score, 6) for result in results] == [
        1.0,
        round(1.0 - (1.0 - math.sqrt(0.5)), 6),
        0.0,
    ]
    assert [result.score for result in results] == sorted(
        (result.score for result in results), reverse=True
    )


def test_the_distance_the_vector_database_reported_is_kept(db_session, collection, library):
    """Both numbers, so the converted one can be checked against the raw one."""
    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    for result in results:
        assert result.score == pytest.approx(1.0 - result.distance)


def test_a_section_pointing_the_other_way_scores_below_zero(db_session, collection):
    document = _document(db_session)
    section = _section(db_session, document, 0, "Nothing to do with it.")
    _store(collection, section, SOUTH)
    db_session.commit()

    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert results[0].score == pytest.approx(-1.0)


# --- the text, which comes from the Main Database -----------------------


def test_the_text_comes_from_the_main_database_not_the_vector_one(db_session, collection, library):
    """The Vector Database never held the text; ON-41 deliberately did not store it."""
    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert results[0].text == "Holiday is 20 days."
    assert collection.documents_seen == [None, None, None]


def test_a_result_carries_what_a_citation_needs(db_session, collection, library):
    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    best = results[0]
    assert best.document == "handbook.pdf"
    assert best.heading == "Holiday"
    assert best.position == 0
    assert best.document_id == library["north"].document_id


def test_a_section_with_no_heading_keeps_none_rather_than_inventing_one(
    db_session, collection, library
):
    results = retrieve(
        "the office", db_session, provider=FixedProvider(EAST), collection=collection
    )

    assert results[0].heading is None


def test_each_result_names_its_own_document(db_session, collection):
    """The normal case: five matches spread over more than one document.

    A fixture with one document in it cannot tell a correct filename from
    a hard-coded one, which is exactly how fault injection found this test
    missing - the fault wrote the fixture's own filename and nothing
    noticed.
    """
    handbook = _document(db_session, "handbook.pdf")
    benefits = _document(db_session, "benefits-2026.pdf")
    first = _section(db_session, handbook, 0, "Holiday is 20 days.", "Holiday")
    second = _section(db_session, benefits, 0, "Dental is covered.", "Dental")
    _store(collection, first, NORTH)
    _store(collection, second, NORTH_EAST)
    db_session.commit()

    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert [result.document for result in results] == ["handbook.pdf", "benefits-2026.pdf"]
    assert [result.document_id for result in results] == [handbook.id, benefits.id]


def test_results_are_read_without_one_query_per_section(db_session, collection):
    """Five sections should not mean five round trips for five filenames.

    `expunge_all` first, and two documents rather than one. Without the
    expunge the rows are still in the session's identity map from building
    them, so `section.document` resolves without touching the database and
    the test passes whether or not the query asked for the documents - it
    measured the fixture, not the code.
    """
    handbook = _document(db_session, "handbook.pdf")
    benefits = _document(db_session, "benefits-2026.pdf")
    _store(collection, _section(db_session, handbook, 0, "Holiday is 20 days."), NORTH)
    _store(collection, _section(db_session, benefits, 0, "Dental is covered."), NORTH_EAST)
    _store(collection, _section(db_session, handbook, 1, "The office is on Main Street."), EAST)
    db_session.commit()
    db_session.expunge_all()

    statements: list[str] = []

    def record(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", record)
    try:
        results = retrieve(
            "holiday", db_session, provider=FixedProvider(NORTH), collection=collection
        )
        # Touch every field a caller would, so a lazy load would show up.
        _ = [(result.document, result.text) for result in results]
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", record)

    selects = [
        statement for statement in statements if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) == 1, f"expected one SELECT, got {len(selects)}: {selects}"


# --- the two stores disagreeing ----------------------------------------


def test_a_vector_whose_section_is_gone_is_dropped(db_session, collection, library):
    """A deleted document can leave vectors behind (TD-28).

    They must not be returned: there is no row to read the text from, so
    the answer would cite a section that no longer exists.
    """
    db_session.delete(library["north"])
    db_session.commit()

    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert [result.section_id for result in results] == [
        library["north_east"].id,
        library["east"].id,
    ]


def test_a_vector_whose_section_is_gone_is_complained_about(
    db_session, collection, library, caplog
):
    """Silently dropping it would hide the two stores drifting apart."""
    stale = library["north"].id
    db_session.delete(library["north"])
    db_session.commit()

    with caplog.at_level(logging.WARNING, logger="app.services.retrieval.service"):
        retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert str(stale) in caplog.text
    assert "Main Database" in caplog.text


def test_an_id_that_is_not_a_section_id_does_not_stop_the_others(
    db_session, collection, library, caplog
):
    collection.rows["not-a-number"] = (NORTH, {"document_id": 1, "position": 0})

    with caplog.at_level(logging.WARNING, logger="app.services.retrieval.service"):
        results = retrieve(
            "holiday", db_session, provider=FixedProvider(NORTH), collection=collection
        )

    assert [result.section_id for result in results] == [
        library["north"].id,
        library["north_east"].id,
        library["east"].id,
    ]
    assert "not-a-number" in caplog.text


# --- how many, and the contract that fixes it ---------------------------


def test_the_contracts_fix_the_number_of_sections_at_five():
    """The literal, not the constant.

    Asserting `retrieve` returns `TOP_K` results would pass for any value
    of TOP_K, which is how a contract-fixed number quietly becomes
    twenty.
    """
    assert TOP_K == 5


def test_only_five_sections_come_back_however_many_match(db_session, collection):
    document = _document(db_session)
    for position in range(9):
        section = _section(db_session, document, position, f"Section {position}.")
        # Fanned out from NORTH, so the ranking is unambiguous.
        angle = position * 0.05
        _store(collection, section, [math.sin(angle), math.cos(angle)])
    db_session.commit()

    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert len(results) == 5
    assert collection.query_calls[0]["n_results"] == 5


def test_fewer_matches_than_five_is_not_padded(db_session, collection, library):
    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert len(results) == 3


def test_an_empty_vector_database_returns_nothing(db_session, collection):
    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert results == []


def test_the_text_is_not_asked_for_from_the_vector_database(db_session, collection, library):
    """`documents` is never written, so asking for it returns a column of nulls."""
    retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert collection.query_calls[0]["include"] == ["distances", "metadatas"]


# --- questions that are not questions -----------------------------------


@pytest.mark.parametrize("question", ["", "   ", "\n\t "])
def test_a_blank_question_is_not_embedded_at_all(db_session, collection, library, question):
    """Embedding whitespace costs a request and returns arbitrary sections."""
    provider = FixedProvider(NORTH)

    assert retrieve(question, db_session, provider=provider, collection=collection) == []
    assert provider.asked == []
    assert collection.query_calls == []


def test_the_question_itself_is_what_gets_embedded(db_session, collection, library):
    provider = FixedProvider(NORTH)

    retrieve("How much holiday do I get?", db_session, provider=provider, collection=collection)

    assert provider.asked == ["How much holiday do I get?"]


# --- failure --------------------------------------------------------------


def test_an_embedding_failure_is_raised_not_turned_into_no_matches(db_session, collection, library):
    """ "Nothing matched" and "nothing could be asked" are different answers.

    The QA Controller (ON-46) turns both into the HR fallback, but only one
    of them is a broken Embedding API, and a service that returned `[]` for
    it would make an outage indistinguishable from an unhelpful question.
    """
    with pytest.raises(EmbeddingError):
        retrieve("holiday", db_session, provider=FailingProvider(), collection=collection)


def test_a_vector_database_failure_is_raised(db_session, collection, library):
    collection.fail_with = RuntimeError("the Vector Database is not answering")

    with pytest.raises(RuntimeError):
        retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)


# --- what the service is and is not -------------------------------------


def test_retrieval_does_not_apply_a_relevance_threshold(db_session, collection):
    """ON-46's job, not this one.

    A section pointing almost the opposite way is still returned, with the
    low score that says so. Dropping it here would take the decision away
    from the component the contracts give it to, and hide the number that
    decision is made on.
    """
    document = _document(db_session)
    section = _section(db_session, document, 0, "Nothing relevant at all.")
    _store(collection, section, SOUTH)
    db_session.commit()

    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH), collection=collection)

    assert len(results) == 1
    assert results[0].score < 0


def test_a_retrieved_section_cannot_be_edited_after_the_fact():
    """Frozen, so nothing downstream can rewrite the text it was handed."""
    result = RetrievedSection(
        section_id=1,
        document_id=2,
        document="handbook.pdf",
        heading=None,
        position=0,
        text="Holiday is 20 days.",
        score=1.0,
        distance=0.0,
    )

    with pytest.raises(FrozenInstanceError):
        result.text = "Holiday is 40 days."  # type: ignore[misc]


def test_retrieval_reaches_the_configured_collection_when_not_given_one(
    db_session, collection, library, monkeypatch
):
    """The `collection` argument is for tests; the service finds its own."""
    monkeypatch.setattr(retrieval, "get_collection", lambda: collection)

    results = retrieve("holiday", db_session, provider=FixedProvider(NORTH))

    assert [result.section_id for result in results] == [
        library["north"].id,
        library["north_east"].id,
        library["east"].id,
    ]
