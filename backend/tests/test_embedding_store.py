"""Writing section vectors to the Vector Database (ON-41, U4).

Against the fake collection from `conftest.py`, which enforces the two
rules the real ChromaDB enforces and that this code could otherwise break
without noticing: ids are strings, and every vector in a collection has
the same width.
"""

import pytest

from app.db.models import Section
from app.services.embedding import store
from app.services.embedding.store import (
    MAX_WRITE_BATCH,
    forget_document,
    remember_sections,
    section_metadata,
)


def section(identifier: int, *, document_id: int = 1, position: int = 0, heading=None) -> Section:
    """A Section row with an id, without needing a database.

    The id is the thing under test - it is what the vector is stored
    under - so it is set explicitly rather than left to a sequence.
    """
    return Section(
        id=identifier,
        document_id=document_id,
        position=position,
        heading=heading,
        text=f"the text of section {identifier}",
    )


# --- what gets written -------------------------------------------------


def test_a_vector_is_keyed_by_the_section_id_not_its_position(collection):
    # The two are easy to confuse and both are small integers. Keying by
    # position would collide across documents and point every citation at
    # whichever document was uploaded last.
    remember_sections([section(41, document_id=3, position=0)], [[0.1]])

    assert set(collection.rows) == {"41"}


def test_it_writes_ids_metadata_and_vectors(collection):
    remember_sections([section(7, document_id=3, position=2, heading="Leave")], [[0.1, 0.2]])

    assert collection.count() == 1
    assert collection.vector_for("7") == [0.1, 0.2]
    assert collection.metadata_for("7") == {"document_id": 3, "position": 2, "heading": "Leave"}


def test_a_section_with_no_heading_gets_an_empty_one(collection):
    # ChromaDB metadata cannot hold null, and a missing key would make the
    # metadata shape differ from row to row.
    remember_sections([section(7, heading=None)], [[0.1, 0.2]])

    assert collection.metadata_for("7")["heading"] == ""


def test_the_section_text_is_not_stored_in_the_vector_database(collection):
    # The Main Database holds the approved copy. Two stores holding the
    # same text is two stores that can disagree about what a citation
    # says, and the one with no transaction around it is the one that
    # would drift.
    remember_sections([section(7)], [[0.1, 0.2]])

    assert collection.documents_seen == [None]


def test_it_reports_how_many_it_wrote(collection):
    written = remember_sections([section(1), section(2, position=1)], [[0.1], [0.2]])

    assert written == 2


# --- refusing to guess -------------------------------------------------


def test_more_sections_than_vectors_is_refused(collection):
    with pytest.raises(ValueError, match="every section"):
        remember_sections([section(1), section(2, position=1)], [[0.1]])

    assert collection.count() == 0


def test_more_vectors_than_sections_is_refused(collection):
    with pytest.raises(ValueError, match="every section"):
        remember_sections([section(1)], [[0.1], [0.2]])

    assert collection.count() == 0


def test_nothing_to_write_writes_nothing(collection):
    assert remember_sections([], []) == 0
    assert collection.upsert_calls == []


# --- batching ----------------------------------------------------------


def test_the_batch_size_stays_well_inside_chromadbs_limit():
    """Pinned to the literal rather than read from the module.

    This test used to build `MAX_WRITE_BATCH + 15` sections and expect
    `[MAX_WRITE_BATCH, 15]`, which moves with the constant: fault
    injection raised the batch size to 100,000 and the test followed it
    and passed. ChromaDB's server-side maximum is 5461 on the pinned
    version and exceeding it fails the whole write, so the value itself
    is the thing under test.
    """
    assert MAX_WRITE_BATCH == 500


def test_a_long_document_is_written_in_batches(collection, monkeypatch):
    # The splitting, independent of the number it splits on - seven
    # sections in threes, so an off-by-one at a boundary shows up as a
    # wrong call pattern rather than a slow test.
    monkeypatch.setattr(store, "MAX_WRITE_BATCH", 3)
    sections = [section(index + 1, position=index) for index in range(7)]
    vectors = [[float(index)] for index in range(7)]

    remember_sections(sections, vectors)

    assert collection.upsert_calls == [3, 3, 1]
    assert collection.count() == 7
    # Every section still paired with its own vector across the splits.
    assert collection.vector_for("1") == [0.0]
    assert collection.vector_for("7") == [6.0]


def test_writing_the_same_sections_twice_is_harmless(collection):
    # A retried upload must not fail on a duplicate id and leave a
    # document whose vectors are half written.
    sections = [section(7)]
    remember_sections(sections, [[0.1, 0.2]])
    remember_sections(sections, [[0.3, 0.4]])

    assert collection.count() == 1
    assert collection.vector_for("7") == [0.3, 0.4]


# --- forgetting --------------------------------------------------------


def test_forgetting_a_document_removes_only_its_own_vectors(collection):
    remember_sections(
        [section(1, document_id=1), section(2, document_id=2, position=0)],
        [[0.1], [0.2]],
    )

    forget_document(1)

    assert set(collection.rows) == {"2"}


def test_forgetting_a_document_with_no_vectors_is_a_no_op(collection):
    forget_document(99)

    assert collection.count() == 0


# --- metadata ----------------------------------------------------------


def test_section_metadata_holds_no_nulls():
    metadata = section_metadata(section(1, heading=None))

    assert None not in metadata.values()
