"""The Logging Service's chat half (ON-47, step 9).

Small, and worth testing on its own rather than only through the
endpoint, because three later features read what it writes: escalation
points at a chat log, feedback rates one, and ON-24 counts fallbacks off
the table. A column written wrongly here is a feature that fails much
later, somewhere that looks unrelated.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import select

from app.db.models import ChatLog, User
from app.services.llm.gateway import Citation
from app.services.logs import citation_rows, save_chat


@pytest.fixture
def employee(db_session) -> User:
    user = User(
        email="alex@example.com",
        full_name="Alex Rivera",
        password_hash="scrypt:not-a-real-hash",
        role="employee",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _save(db_session, employee, **overrides):
    defaults = {
        "question": "How much holiday do I get?",
        "answer": "Twenty days.",
        "citations": [Citation(section_id=7, heading="Holiday", document="handbook.pdf")],
        "fallback": False,
    }
    return save_chat(db_session, user_id=employee.id, **(defaults | overrides))


# --- what gets written ---------------------------------------------------


def test_the_question_and_the_answer_are_saved(db_session, employee):
    _save(db_session, employee)
    db_session.commit()

    saved = db_session.scalars(select(ChatLog)).one()
    assert saved.question == "How much holiday do I get?"
    assert saved.answer == "Twenty days."
    assert saved.user_id == employee.id


def test_citations_are_saved_as_plain_json(db_session, employee):
    _save(db_session, employee)
    db_session.commit()

    assert db_session.scalars(select(ChatLog)).one().citations == [
        {"section_id": 7, "heading": "Holiday", "document": "handbook.pdf"}
    ]


def test_the_order_of_the_citations_is_kept(db_session, employee):
    """The Gateway accepted them in the order the model used them."""
    _save(
        db_session,
        employee,
        citations=[
            Citation(section_id=9, heading="Nine"),
            Citation(section_id=3, heading="Three"),
            Citation(section_id=5, heading="Five"),
        ],
    )
    db_session.commit()

    saved = db_session.scalars(select(ChatLog)).one()
    assert [row["section_id"] for row in saved.citations] == [9, 3, 5]


def test_a_fallback_is_recorded_as_one(db_session, employee):
    _save(db_session, employee, fallback=True, citations=[])
    db_session.commit()

    saved = db_session.scalars(select(ChatLog)).one()
    assert saved.fallback is True
    assert saved.citations == []


def test_an_answer_is_not_recorded_as_a_fallback(db_session, employee):
    _save(db_session, employee)
    db_session.commit()

    assert db_session.scalars(select(ChatLog)).one().fallback is False


def test_the_saved_row_comes_back_with_its_id(db_session, employee):
    """The caller needs it for the response; the Chat Page escalates by it."""
    chat_log = _save(db_session, employee)

    assert chat_log.id is not None
    assert chat_log.id > 0


# --- the shape of a citation row -----------------------------------------


def test_a_citation_row_holds_exactly_three_fields():
    rows = citation_rows([Citation(section_id=1, heading="Holiday", document="handbook.pdf")])

    assert rows == [{"section_id": 1, "heading": "Holiday", "document": "handbook.pdf"}]


def test_a_citation_with_no_heading_keeps_none_rather_than_inventing_one():
    assert citation_rows([Citation(section_id=1, heading=None)]) == [
        {"section_id": 1, "heading": None, "document": None}
    ]


def test_no_citations_is_an_empty_list_not_null():
    """The column is JSON and the Chat Page iterates it."""
    assert citation_rows([]) == []


def test_a_field_added_to_citation_is_not_written_out_by_accident():
    """Spelled out by hand rather than with `asdict`, and this is why.

    A field added to `Citation` for some internal purpose - a score, a
    distance, a prompt offset - would otherwise start appearing in every
    chat log row and in every response to every browser, with nothing
    anywhere deciding that it should.
    """

    @dataclass(frozen=True)
    class CitationWithExtra:
        section_id: int
        heading: str | None = None
        document: str | None = None
        internal_note: str = "not for the browser"

    rows = citation_rows([CitationWithExtra(section_id=1)])

    assert rows == [{"section_id": 1, "heading": None, "document": None}]
    assert "internal_note" not in rows[0]


# --- the transaction belongs to the caller --------------------------------


def test_the_write_is_not_committed_here(db_session, employee):
    """The endpoint is mid-request and is the only thing that knows if it worked.

    Committing here would also hand back an id from a transaction the
    caller can no longer roll back, which reads fine and leaves a chat log
    for a request that failed.
    """
    _save(db_session, employee)
    db_session.rollback()

    assert db_session.scalars(select(ChatLog)).all() == []
