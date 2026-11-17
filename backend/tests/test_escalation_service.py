"""The Escalation Service on its own (ON-20, E1 to E2).

`test_escalations_api.py` drives this through HTTP, which is the right
way to test the endpoint and the wrong way to test the service: the
endpoint commits, and a commit flushes, so a service that forgot to
flush or committed on its caller's behalf behaves identically from out
there. Fault injection said so — four faults survived a full pass
through the API and die here.

The transaction boundary is the point. The service flushes and the
caller commits, because the caller is mid-request and is the only thing
that knows whether the whole of it succeeded.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import ChatLog, Escalation, User
from app.services.escalations import NoSuchAnswer, NotAFallback, open_escalation

FALLBACK_ANSWER = "I could not find an answer to that in the approved HR documents."


@pytest.fixture
def people(db_session) -> dict[str, User]:
    users = {}
    for key, email, role in (
        ("employee", "alex@example.com", "employee"),
        ("colleague", "sam@example.com", "employee"),
    ):
        user = User(
            email=email,
            full_name=key.title(),
            password_hash="scrypt:not-a-real-hash",
            role=role,
        )
        db_session.add(user)
        db_session.flush()
        users[key] = user
    db_session.commit()
    return users


def _chat(db_session, owner: User, *, fallback=True, question="Am I paid for jury duty?"):
    chat_log = ChatLog(
        user_id=owner.id,
        question=question,
        answer=FALLBACK_ANSWER if fallback else "Yes.",
        citations=[],
        fallback=fallback,
    )
    db_session.add(chat_log)
    db_session.commit()
    return chat_log


# --- the transaction belongs to the caller -------------------------------


def test_the_write_is_not_committed_here(db_session, people):
    """The endpoint is mid-request and may still fail after this returns.

    Committing here would also mean the row's id came back from a
    transaction the caller can no longer roll back, which reads fine and
    leaves an escalation in HR's inbox for a request that failed.
    """
    chat_log = _chat(db_session, people["employee"])

    open_escalation(db_session, user_id=people["employee"].id, chat_log_id=chat_log.id)
    db_session.rollback()

    assert db_session.scalars(select(Escalation)).all() == []


def test_the_row_comes_back_with_its_id_before_any_commit(db_session, people):
    """Flushed, so the caller has an id to put in its response.

    Through the endpoint this is invisible - its commit flushes anyway -
    which is exactly why it is tested here.
    """
    chat_log = _chat(db_session, people["employee"])

    escalation = open_escalation(db_session, user_id=people["employee"].id, chat_log_id=chat_log.id)

    assert escalation.id is not None
    assert escalation.id > 0


# --- asking twice ----------------------------------------------------------


def test_the_same_question_twice_returns_the_same_escalation(db_session, people):
    chat_log = _chat(db_session, people["employee"])

    first = open_escalation(db_session, user_id=people["employee"].id, chat_log_id=chat_log.id)
    second = open_escalation(db_session, user_id=people["employee"].id, chat_log_id=chat_log.id)

    assert first.id == second.id
    assert len(db_session.scalars(select(Escalation)).all()) == 1


def test_a_resolved_escalation_is_not_handed_back(db_session, people):
    """HR has already answered this one; asking again is a new question.

    Returning the resolved row would show the employee a reply to a
    question they have just asked afresh, and HR would never see the new
    one. Only an *open* escalation counts as the same question still
    waiting.
    """
    chat_log = _chat(db_session, people["employee"])
    done = Escalation(
        user_id=people["employee"].id,
        chat_log_id=chat_log.id,
        question=chat_log.question,
        status="resolved",
        hr_reply="Yes, up to ten days.",
    )
    db_session.add(done)
    db_session.commit()

    fresh = open_escalation(db_session, user_id=people["employee"].id, chat_log_id=chat_log.id)
    db_session.commit()

    assert fresh.id != done.id
    assert fresh.status == "open"
    assert len(db_session.scalars(select(Escalation)).all()) == 2


def test_an_escalation_belonging_to_somebody_else_is_not_handed_back(db_session, people):
    """Defensive, against a row this API cannot create.

    Ownership is already checked before the lookup runs, so a colleague's
    escalation against this employee's chat log can only come from a data
    error - seeded directly here, because that is the only way it
    happens. Without the `user_id` filter the service would hand one
    person another person's escalation, and E4 shows HR's reply against
    it.
    """
    chat_log = _chat(db_session, people["employee"])
    theirs = Escalation(
        user_id=people["colleague"].id,
        chat_log_id=chat_log.id,
        question=chat_log.question,
        status="open",
    )
    db_session.add(theirs)
    db_session.commit()

    mine = open_escalation(db_session, user_id=people["employee"].id, chat_log_id=chat_log.id)
    db_session.commit()

    assert mine.id != theirs.id
    assert mine.user_id == people["employee"].id


# --- the rules ---------------------------------------------------------------


def test_the_question_is_read_from_the_chat_log(db_session, people):
    chat_log = _chat(db_session, people["employee"], question="Is there a commuter benefit?")

    escalation = open_escalation(db_session, user_id=people["employee"].id, chat_log_id=chat_log.id)

    assert escalation.question == "Is there a commuter benefit?"


def test_it_is_recorded_against_whoever_escalated_it(db_session, people):
    """The colleague, who is deliberately not the first user row.

    Asserting this with the first employee proves nothing: they are user
    1, so a hard-coded `user_id=1` reads as correct. Fault injection has
    now caught this same shape of mistake three times in this project.
    """
    chat_log = _chat(db_session, people["colleague"])

    escalation = open_escalation(
        db_session, user_id=people["colleague"].id, chat_log_id=chat_log.id
    )

    assert people["colleague"].id != 1, "the fixture stopped making this test meaningful"
    assert escalation.user_id == people["colleague"].id


def test_a_colleagues_answer_cannot_be_escalated(db_session, people):
    theirs = _chat(db_session, people["colleague"])

    with pytest.raises(NoSuchAnswer):
        open_escalation(db_session, user_id=people["employee"].id, chat_log_id=theirs.id)


def test_an_answer_that_does_not_exist_is_refused(db_session, people):
    with pytest.raises(NoSuchAnswer):
        open_escalation(db_session, user_id=people["employee"].id, chat_log_id=9999)


def test_an_answered_question_is_refused(db_session, people):
    answered = _chat(db_session, people["employee"], fallback=False)

    with pytest.raises(NotAFallback):
        open_escalation(db_session, user_id=people["employee"].id, chat_log_id=answered.id)


def test_nothing_is_written_when_it_is_refused(db_session, people):
    answered = _chat(db_session, people["employee"], fallback=False)

    with pytest.raises(NotAFallback):
        open_escalation(db_session, user_id=people["employee"].id, chat_log_id=answered.id)

    assert db_session.scalars(select(Escalation)).all() == []
