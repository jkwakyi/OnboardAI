"""POST /api/escalations (ON-20, E1 to E2).

The endpoint and the Escalation Service behind it, through a real HTTP
client against a throwaway database.

Three of these matter more than the rest, and none of them is the happy
path:

* **The question comes from the chat log, not the request.** Otherwise
  HR's inbox fills with questions nobody asked, each one linked to a
  chat log that says something else.
* **An answer belongs to the person escalating it.** Auth Check guards
  routes, not rows (TD-21), so this is the only thing between an
  employee and a colleague's conversation - and E4 shows HR's reply
  against the chat, so escalating somebody else's question means reading
  the answer to it.
* **Only a fallback can be escalated.** The Chat Page only draws the
  button on one, but a button that is absent is not a rule.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api.auth_check import BEARER
from app.db.models import ChatLog, Escalation, User
from app.db.session import get_session
from app.main import create_app
from app.services.auth import ensure_account, issue_token

ESCALATIONS = "/api/escalations"

FALLBACK_ANSWER = (
    "I could not find an answer to that in the approved HR documents. "
    "Please send the question to HR and someone will reply to you here."
)


@pytest.fixture
def accounts(auth_env, db_session):
    for email, name, role in (
        ("employee@onboardai.example", "Alex Rivera", "employee"),
        ("colleague@onboardai.example", "Sam Okafor", "employee"),
        ("hr@onboardai.example", "Jordan Blake", "hr_administrator"),
    ):
        ensure_account(
            db_session, email=email, full_name=name, role=role, password="a development password"
        )
    users = db_session.scalars(select(User)).all()
    return {user.email.split("@")[0]: user for user in users}


@pytest.fixture
def api(auth_env, db_session, accounts):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client


def headers_for(accounts, who: str = "employee") -> dict[str, str]:
    user = accounts[who]
    token = issue_token(user.id, email=user.email, full_name=user.full_name, role=user.role)
    return {"Authorization": f"{BEARER} {token}"}


def _chat(db_session, owner: User, *, fallback: bool = True, question="Am I paid for jury duty?"):
    chat_log = ChatLog(
        user_id=owner.id,
        question=question,
        answer=FALLBACK_ANSWER if fallback else "Yes, for up to ten days.",
        citations=[] if fallback else [{"section_id": 1, "heading": "Jury", "document": "h.txt"}],
        fallback=fallback,
    )
    db_session.add(chat_log)
    db_session.commit()
    return chat_log


def send(api, accounts, chat_log_id: int, who: str = "employee"):
    return api.post(
        ESCALATIONS, json={"chat_log_id": chat_log_id}, headers=headers_for(accounts, who)
    )


# --- the happy path ------------------------------------------------------


def test_a_fallback_question_can_be_sent_to_hr(api, accounts, db_session):
    chat_log = _chat(db_session, accounts["employee"])

    response = send(api, accounts, chat_log.id)

    assert response.status_code == 201
    body = response.json()
    assert body["question"] == "Am I paid for jury duty?"
    assert body["status"] == "open"
    assert body["chat_log_id"] == chat_log.id


def test_it_is_saved_as_an_open_escalation(api, accounts, db_session):
    """E2: open, waiting for HR, with nobody having resolved it."""
    chat_log = _chat(db_session, accounts["employee"])

    send(api, accounts, chat_log.id)

    saved = db_session.scalars(select(Escalation)).one()
    assert saved.status == "open"
    assert saved.user_id == accounts["employee"].id
    assert saved.chat_log_id == chat_log.id
    assert saved.hr_reply is None
    assert saved.resolved_by_id is None
    assert saved.resolved_at is None


def test_it_points_back_at_the_answer_it_came_from(api, accounts, db_session):
    """E4 shows HR's reply against the right message, and this is the link."""
    chat_log = _chat(db_session, accounts["employee"])

    send(api, accounts, chat_log.id)

    assert db_session.scalars(select(Escalation)).one().chat_log_id == chat_log.id


def test_an_hr_administrator_may_send_one_too(api, accounts, db_session):
    """The contracts put both roles on the Chat Page, so both can fall back."""
    chat_log = _chat(db_session, accounts["hr"])

    assert send(api, accounts, chat_log.id, who="hr").status_code == 201


# --- the question is the server's to decide --------------------------------


def test_the_question_comes_from_the_chat_log_not_the_request(api, accounts, db_session):
    """The one that matters most.

    A caller sending their own `question` must not be able to put words
    in HR's inbox. The field is not read at all, so an extra one in the
    body changes nothing.
    """
    chat_log = _chat(db_session, accounts["employee"], question="Am I paid for jury duty?")

    response = api.post(
        ESCALATIONS,
        json={"chat_log_id": chat_log.id, "question": "Please approve my 10k expense claim"},
        headers=headers_for(accounts),
    )

    assert response.status_code == 201
    assert response.json()["question"] == "Am I paid for jury duty?"
    assert db_session.scalars(select(Escalation)).one().question == "Am I paid for jury duty?"


def test_the_status_is_not_the_callers_to_set(api, accounts, db_session):
    """E2 says open. A resolved escalation nobody resolved is worse than none."""
    chat_log = _chat(db_session, accounts["employee"])

    response = api.post(
        ESCALATIONS,
        json={"chat_log_id": chat_log.id, "status": "resolved", "hr_reply": "Sorted."},
        headers=headers_for(accounts),
    )

    assert response.status_code == 201
    saved = db_session.scalars(select(Escalation)).one()
    assert saved.status == "open"
    assert saved.hr_reply is None


# --- whose answer is it ------------------------------------------------------


def test_a_colleagues_answer_cannot_be_escalated(api, accounts, db_session):
    """Auth Check guards routes, not rows (TD-21).

    And escalating somebody else's question is not only writing: E4 shows
    HR's reply against the chat it belongs to, so it is a way of reading
    the answer to a question you were never told about.
    """
    theirs = _chat(db_session, accounts["colleague"], question="Is my probation over?")

    response = send(api, accounts, theirs.id, who="employee")

    assert response.status_code == 404
    assert db_session.scalars(select(Escalation)).all() == []


def test_an_answer_that_does_not_exist_is_refused(api, accounts):
    assert send(api, accounts, 9999).status_code == 404


def test_a_missing_answer_and_somebody_elses_look_the_same(api, accounts, db_session):
    """Telling them apart is telling somebody which ids are real."""
    theirs = _chat(db_session, accounts["colleague"])

    not_mine = send(api, accounts, theirs.id)
    not_there = send(api, accounts, 9999)

    assert not_mine.status_code == not_there.status_code == 404
    assert not_mine.json()["detail"] == not_there.json()["detail"]


# --- only a fallback ----------------------------------------------------------


def test_an_answered_question_cannot_be_sent_to_hr(api, accounts, db_session):
    """ "Sends a question that got a fallback answer to HR".

    Escalating an answered one puts a solved question in front of HR with
    nothing to say it was solved.
    """
    answered = _chat(db_session, accounts["employee"], fallback=False)

    response = send(api, accounts, answered.id)

    assert response.status_code == 409
    assert db_session.scalars(select(Escalation)).all() == []


def test_the_refusal_says_why_in_words_an_employee_can_read(api, accounts, db_session):
    answered = _chat(db_session, accounts["employee"], fallback=False)

    detail = send(api, accounts, answered.id).json()["detail"]

    assert "answered" in detail.lower()
    assert "fallback" not in detail.lower(), "that is our word, not theirs"


# --- asking twice ---------------------------------------------------------------


def test_sending_the_same_question_twice_does_not_make_two(api, accounts, db_session):
    """A double click must not put the same question in HR's inbox twice."""
    chat_log = _chat(db_session, accounts["employee"])

    first = send(api, accounts, chat_log.id)
    second = send(api, accounts, chat_log.id)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(db_session.scalars(select(Escalation)).all()) == 1


def test_two_different_questions_are_two_escalations(api, accounts, db_session):
    first = _chat(db_session, accounts["employee"], question="Am I paid for jury duty?")
    second = _chat(db_session, accounts["employee"], question="Is there a commuter benefit?")

    send(api, accounts, first.id)
    send(api, accounts, second.id)

    assert len(db_session.scalars(select(Escalation)).all()) == 2


# --- validation and auth ----------------------------------------------------------


def test_a_request_with_no_answer_named_is_refused(api, accounts):
    assert api.post(ESCALATIONS, json={}, headers=headers_for(accounts)).status_code == 422


def test_an_id_that_is_not_a_number_is_refused(api, accounts):
    response = api.post(
        ESCALATIONS, json={"chat_log_id": "the first one"}, headers=headers_for(accounts)
    )

    assert response.status_code == 422


def test_an_id_of_zero_is_refused_before_the_database_is_asked(api, accounts):
    assert (
        api.post(ESCALATIONS, json={"chat_log_id": 0}, headers=headers_for(accounts)).status_code
        == 422
    )


def test_the_endpoint_is_behind_auth_check(api):
    assert api.post(ESCALATIONS, json={"chat_log_id": 1}).status_code == 401


def test_a_token_for_an_account_that_is_gone_is_refused(api, accounts, db_session):
    """TD-19: a token outlives the account it names.

    Forged against an id that was never in the table rather than by
    deleting a user, because a user with chat logs cannot be deleted -
    the foreign key is RESTRICT, which is the schema doing its job. The
    token is signed and valid; only the account is missing.
    """
    chat_log = _chat(db_session, accounts["employee"])
    gone = issue_token(9999, email="gone@example.com", full_name="Gone", role="employee")

    response = api.post(
        ESCALATIONS,
        json={"chat_log_id": chat_log.id},
        headers={"Authorization": f"{BEARER} {gone}"},
    )

    assert response.status_code == 401
    assert db_session.scalars(select(Escalation)).all() == []


# --- failure -----------------------------------------------------------------------


def test_nothing_is_left_behind_when_it_cannot_be_saved(api, accounts, db_session, monkeypatch):
    chat_log = _chat(db_session, accounts["employee"])

    def explode():
        raise OperationalError("COMMIT", {}, Exception("the database went away"))

    monkeypatch.setattr(db_session, "commit", explode)

    response = send(api, accounts, chat_log.id)

    assert response.status_code == 500
    monkeypatch.undo()
    assert db_session.scalars(select(Escalation)).all() == []


# --- what the endpoint gives back -----------------------------------------------------


def test_the_response_does_not_carry_fields_that_are_always_empty(api, accounts, db_session):
    """A field that is always null is a field somebody writes code against."""
    chat_log = _chat(db_session, accounts["employee"])

    body = send(api, accounts, chat_log.id).json()

    assert set(body) == {"id", "chat_log_id", "question", "status", "created_at"}


def test_only_the_three_endpoints_the_contracts_define_exist(api, accounts):
    """GET and PATCH are ON-21 and ON-22, and are not here yet.

    An endpoint that exists and does nothing is worse than one that is
    absent, because a client finds it and believes it.
    """
    # 405 for GET: the path is routed, that method is not.
    assert api.get(ESCALATIONS, headers=headers_for(accounts)).status_code == 405
    # 404 for PATCH: there is no route at that path at all, so nothing -
    # not even Auth Check, which is attached to the router - runs.
    assert api.patch(f"{ESCALATIONS}/1", headers=headers_for(accounts)).status_code == 404
