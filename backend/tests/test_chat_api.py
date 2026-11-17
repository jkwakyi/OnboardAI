"""POST /api/chat/ask (ON-47, steps 1 to 9).

The endpoint through a real HTTP client, against a throwaway database and
a fake Vector Database. The role rule belongs to Auth Check and is tested
in `test_auth_check.py`; the threshold decision belongs to the QA
Controller and is tested in `test_qa_controller.py`. What is checked here
is the endpoint's own two promises:

* **The AI path never produces an error status.** "A timeout, provider
  error or invalid output from the LLM is not an error for the employee:
  POST /api/chat/ask returns fallback: true." Every way the model and the
  retrieval path can fail comes back 200.
* **Every answer is saved, and the id it returns is real.** The Chat Page
  rates answers and escalates fallbacks by that id, so an id for a row
  that does not exist would fail in front of the employee, after they had
  already been told to ask HR.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api.auth_check import BEARER
from app.db.models import ChatLog, Document, Section, User
from app.db.session import get_session
from app.main import create_app
from app.services.auth import ensure_account, issue_token
from app.services.llm import PROVIDERS
from app.services.llm.gateway import HR_FALLBACK_MESSAGE, MAX_QUESTION_CHARACTERS
from app.services.llm.provider import LLMError, LLMProvider

ASK = "/api/chat/ask"

NORTH = [0.0, 1.0]
EAST = [1.0, 0.0]


class ScriptedLLM(LLMProvider):
    """A provider the tests can aim, shared through `PROVIDERS`.

    The endpoint builds its own `QAController`, which builds its own
    Gateway around `get_provider()` - that is the arrangement the Chat API
    is meant to have, so the test reaches it the way a deployment would,
    by changing which provider is registered.
    """

    output: str | None = None
    failure: Exception | None = None
    prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        type(self).prompts.append(prompt)
        if type(self).failure is not None:
            raise type(self).failure
        if type(self).output is not None:
            return type(self).output
        marker = [line for line in prompt.splitlines() if line.startswith("[section:")]
        first = marker[0].split("]")[0].removeprefix("[section:") if marker else "0"
        return (
            '{"answer": "Twenty days of holiday a year.", '
            f'"citations": [{{"section_id": {first}, "heading": "Holiday"}}]}}'
        )


@pytest.fixture
def scripted(monkeypatch):
    ScriptedLLM.output = None
    ScriptedLLM.failure = None
    ScriptedLLM.prompts = []
    monkeypatch.setitem(PROVIDERS, "mock", ScriptedLLM)
    return ScriptedLLM


@pytest.fixture
def accounts(auth_env, db_session):
    for email, name, role in (
        ("employee@onboardai.example", "Alex Rivera", "employee"),
        ("hr@onboardai.example", "Jordan Blake", "hr_administrator"),
    ):
        ensure_account(
            db_session, email=email, full_name=name, role=role, password="a development password"
        )
    return {user.role: user for user in db_session.scalars(select(User)).all()}


@pytest.fixture
def handbook(db_session, accounts, collection):
    """Two sections with known vectors, in both stores."""
    document = Document(
        filename="handbook.pdf",
        content_type="pdf",
        stored_path="backend/storage/documents/handbook.pdf",
        size_bytes=2048,
        uploaded_by_id=accounts["hr_administrator"].id,
    )
    db_session.add(document)
    db_session.flush()

    rows = []
    for position, (heading, text, vector) in enumerate(
        [
            ("Holiday", "Every employee gets twenty days of holiday a year.", NORTH),
            ("The Office", "The office is on Main Street.", EAST),
        ]
    ):
        section = Section(document=document, position=position, heading=heading, text=text)
        db_session.add(section)
        db_session.flush()
        collection.upsert(
            ids=[str(section.id)],
            embeddings=[vector],
            metadatas=[{"document_id": document.id, "position": position}],
        )
        rows.append(section)
    db_session.commit()
    return rows


@pytest.fixture
def aimed_at_north(monkeypatch):
    """Every question embeds to NORTH, so the holiday section scores 1.0."""
    monkeypatch.setattr(
        "app.services.retrieval.service.embed_question",
        lambda question, provider=None, settings=None: NORTH,
    )


@pytest.fixture
def api(auth_env, db_session, accounts, collection, scripted, monkeypatch):
    """The endpoint, with both databases replaced by throwaways."""
    monkeypatch.setattr("app.services.retrieval.service.get_collection", lambda: collection)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client


def headers_for(accounts, role: str = "employee") -> dict[str, str]:
    user = accounts[role]
    token = issue_token(user.id, email=user.email, full_name=user.full_name, role=user.role)
    return {"Authorization": f"{BEARER} {token}"}


def ask(api, accounts, question="How much holiday do I get?", role="employee"):
    return api.post(ASK, json={"question": question}, headers=headers_for(accounts, role))


# --- the answer ---------------------------------------------------------


def test_an_employee_gets_an_answer_with_citations(api, accounts, handbook, aimed_at_north):
    response = ask(api, accounts)

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Twenty days of holiday a year."
    assert body["fallback"] is False
    assert body["citations"][0]["section_id"] == handbook[0].id


def test_a_citation_carries_what_makes_it_followable(api, accounts, handbook, aimed_at_north):
    """The heading and document come from the retrieved section, not the model.

    ScriptedLLM sends a heading of its own and no document at all; both
    are replaced by the Gateway from what was actually retrieved, which
    is what stops a citation being mislabelled even when its id is right.
    """
    citation = ask(api, accounts).json()["citations"][0]

    assert citation["heading"] == "Holiday"
    assert citation["document"] == "handbook.pdf"


def test_an_hr_administrator_can_ask_too(api, accounts, handbook, aimed_at_north):
    """The contracts put both roles on the Chat Page."""
    assert ask(api, accounts, role="hr_administrator").status_code == 200


def test_the_question_reaches_the_model_with_the_retrieved_text(
    api, accounts, handbook, aimed_at_north, scripted
):
    ask(api, accounts, question="How much holiday do I get?")

    prompt = scripted.prompts[0]
    assert "How much holiday do I get?" in prompt
    assert "Every employee gets twenty days of holiday a year." in prompt


# --- step 9: the chat is saved ------------------------------------------


def test_the_chat_is_saved(api, accounts, db_session, handbook, aimed_at_north):
    response = ask(api, accounts)

    saved = db_session.scalars(select(ChatLog)).one()
    assert saved.question == "How much holiday do I get?"
    assert saved.answer == "Twenty days of holiday a year."
    assert saved.fallback is False
    assert saved.user_id == accounts["employee"].id
    assert response.json()["id"] == saved.id


def test_the_chat_is_recorded_against_whoever_asked(
    api, accounts, db_session, handbook, aimed_at_north
):
    """The HR administrator, who is deliberately not the first user row.

    Asserting this with the employee alone proves nothing: the employee
    is user 1, so a hard-coded `user_id=1` reads as correct. Fault
    injection pointed that out - the same shape of mistake as a fixture
    whose only document is called handbook.pdf.
    """
    ask(api, accounts, role="hr_administrator")

    administrator = accounts["hr_administrator"]
    assert administrator.id != 1, "the fixture stopped making this test meaningful"
    assert db_session.scalars(select(ChatLog)).one().user_id == administrator.id


def test_the_chat_survives_the_end_of_the_request(
    api, accounts, db_session, handbook, aimed_at_north
):
    """Committed, not merely flushed.

    The tests share one session with the endpoint, so a flushed row is
    visible to them whether or not anything committed - which is how a
    missing commit passes every other test in this file. A rollback
    afterwards is the only thing that tells the two apart, and without
    the commit the employee's answer vanishes the moment the request
    ends, taking the id they were just handed with it.
    """
    returned = ask(api, accounts).json()["id"]

    db_session.rollback()

    assert db_session.get(ChatLog, returned) is not None


def test_the_saved_citations_are_the_ones_the_gateway_accepted(
    api, accounts, db_session, handbook, aimed_at_north
):
    ask(api, accounts)

    saved = db_session.scalars(select(ChatLog)).one()
    assert saved.citations == [
        {"section_id": handbook[0].id, "heading": "Holiday", "document": "handbook.pdf"}
    ]


def test_a_fallback_is_saved_too(api, accounts, db_session, handbook, monkeypatch):
    """ON-24 counts the fallback rate off this table.

    A fallback that was not written is a fallback that did not happen as
    far as any report is concerned, which flatters the number in the one
    direction nobody would check.
    """
    monkeypatch.setattr(
        "app.services.retrieval.service.embed_question",
        lambda question, provider=None, settings=None: [-1.0, 0.0],
    )

    response = ask(api, accounts, question="What is the weather?")

    saved = db_session.scalars(select(ChatLog)).one()
    assert saved.fallback is True
    assert saved.answer == HR_FALLBACK_MESSAGE
    assert saved.citations == []
    assert response.json()["id"] == saved.id


def test_the_id_that_comes_back_is_a_row_that_exists(
    api, accounts, db_session, handbook, aimed_at_north
):
    """The Chat Page rates and escalates by this id.

    An id for a row that is not there would fail against a foreign key in
    front of the employee, after they had already been told to ask HR.
    """
    returned = ask(api, accounts).json()["id"]

    assert db_session.get(ChatLog, returned) is not None


def test_each_question_gets_its_own_row(api, accounts, db_session, handbook, aimed_at_north):
    first = ask(api, accounts, question="How much holiday do I get?").json()["id"]
    second = ask(api, accounts, question="How much holiday is there?").json()["id"]

    assert first != second
    assert len(db_session.scalars(select(ChatLog)).all()) == 2


def test_the_question_is_stored_as_asked_but_trimmed(
    api, accounts, db_session, handbook, aimed_at_north
):
    ask(api, accounts, question="  How much holiday do I get?  ")

    assert db_session.scalars(select(ChatLog)).one().question == "How much holiday do I get?"


# --- the AI path never produces an error status --------------------------


def test_no_good_match_is_a_200_with_fallback_true(api, accounts, handbook, monkeypatch):
    monkeypatch.setattr(
        "app.services.retrieval.service.embed_question",
        lambda question, provider=None, settings=None: [-1.0, 0.0],
    )

    response = ask(api, accounts, question="What is the weather?")

    assert response.status_code == 200
    body = response.json()
    assert body["fallback"] is True
    assert body["answer"] == HR_FALLBACK_MESSAGE
    assert body["citations"] == []


def test_a_provider_error_is_a_200_with_fallback_true(
    api, accounts, handbook, aimed_at_north, scripted
):
    scripted.failure = LLMError("the provider is down")

    response = ask(api, accounts)

    assert response.status_code == 200
    assert response.json()["fallback"] is True


def test_output_that_is_not_json_is_a_200_with_fallback_true(
    api, accounts, handbook, aimed_at_north, scripted
):
    scripted.output = "I am afraid I cannot do that."

    response = ask(api, accounts)

    assert response.status_code == 200
    assert response.json()["fallback"] is True


def test_an_answer_citing_nothing_it_was_given_is_a_200_with_fallback_true(
    api, accounts, handbook, aimed_at_north, scripted
):
    scripted.output = '{"answer": "Forty days.", "citations": [{"section_id": 9999}]}'

    response = ask(api, accounts)

    assert response.status_code == 200
    assert response.json()["fallback"] is True
    assert response.json()["answer"] == HR_FALLBACK_MESSAGE


def test_an_embedding_failure_is_a_200_with_fallback_true(api, accounts, handbook, monkeypatch):
    """The Embedding API being down is not the employee's problem."""

    def explode(*_args, **_kwargs):
        raise RuntimeError("the Embedding API answered 429.")

    monkeypatch.setattr("app.services.retrieval.service.embed_question", explode)

    response = ask(api, accounts)

    assert response.status_code == 200
    assert response.json()["fallback"] is True


def test_an_empty_vector_database_is_a_200_with_fallback_true(
    api, accounts, aimed_at_north, scripted
):
    """Nothing uploaded yet, which is the state of a fresh deployment."""
    response = ask(api, accounts)

    assert response.status_code == 200
    assert response.json()["fallback"] is True
    assert scripted.prompts == []


def test_a_fallback_never_leaks_why_it_happened(api, accounts, handbook, aimed_at_north, scripted):
    """The reason is for the log. An employee gets the same words every time."""
    scripted.failure = LLMError("connection refused to 127.0.0.1:11434")

    body = ask(api, accounts).json()

    assert body["answer"] == HR_FALLBACK_MESSAGE
    assert "11434" not in body["answer"]


# --- what is still an error ----------------------------------------------


def test_a_blank_question_is_refused(api, accounts):
    assert api.post(ASK, json={"question": ""}, headers=headers_for(accounts)).status_code == 422


def test_a_question_of_only_spaces_is_refused(api, accounts):
    """`min_length` counts characters, and a space is a character."""
    response = api.post(ASK, json={"question": "   \n\t "}, headers=headers_for(accounts))

    assert response.status_code == 422


def test_a_question_longer_than_the_gateway_would_read_is_refused(api, accounts):
    """Rather than silently answered from the part that fitted.

    The Gateway truncates at its own limit when it builds the prompt, so
    accepting a longer one means answering a question the employee did
    not ask, with nothing to say it happened.
    """
    response = api.post(
        ASK, json={"question": "x" * (MAX_QUESTION_CHARACTERS + 1)}, headers=headers_for(accounts)
    )

    assert response.status_code == 422


def test_a_question_exactly_at_the_limit_is_accepted(api, accounts, handbook, aimed_at_north):
    response = api.post(
        ASK, json={"question": "x" * MAX_QUESTION_CHARACTERS}, headers=headers_for(accounts)
    )

    assert response.status_code == 200


def test_the_endpoint_is_behind_auth_check(api):
    assert api.post(ASK, json={"question": "How much holiday?"}).status_code == 401


def test_a_token_for_an_account_that_is_gone_is_refused(api, accounts, db_session, handbook):
    user = accounts["employee"]
    headers = headers_for(accounts)
    db_session.delete(user)
    db_session.commit()

    response = api.post(ASK, json={"question": "How much holiday?"}, headers=headers)

    assert response.status_code == 401


def test_nothing_is_saved_when_the_chat_cannot_be_recorded(
    api, accounts, handbook, aimed_at_north, monkeypatch
):
    """A database failure is a 500, not a fallback.

    Retrieval read this same database moments earlier, so a write failing
    now is a real outage rather than the AI path having a bad minute - and
    answering 200 with an id that is not there would break the Chat Page's
    "Send to HR" in front of the employee.
    """
    from app.api import chat as chat_api

    def explode(*_args, **_kwargs):
        raise OperationalError("INSERT", {}, Exception("the database went away"))

    # Patched where the endpoint looked the name up: `app.api.chat` did
    # `from app.services.logs import save_chat`, which binds the function
    # into that module at import, so patching the original would leave
    # the endpoint calling the real one.
    monkeypatch.setattr(chat_api, "save_chat", explode)

    response = ask(api, accounts)

    assert response.status_code == 500
    assert "could not be recorded" in response.json()["detail"]


def test_a_failed_recording_does_not_leave_half_a_chat(
    api, accounts, db_session, handbook, aimed_at_north, monkeypatch
):
    """The row is added and then the commit fails, which is the real shape.

    Patching `save_chat` to raise tests nothing about the rollback: it
    fails before anything is in the session, so there is nothing to undo
    and the endpoint looks correct with the rollback deleted. Failing the
    commit instead leaves a pending row that only the rollback removes.
    """

    def explode():
        raise OperationalError("COMMIT", {}, Exception("the database went away"))

    monkeypatch.setattr(db_session, "commit", explode)

    response = ask(api, accounts)

    assert response.status_code == 500
    # The real commit back, so what is left in the session is what the
    # endpoint left rather than what this test is still breaking.
    monkeypatch.undo()
    assert db_session.scalars(select(ChatLog)).all() == []
