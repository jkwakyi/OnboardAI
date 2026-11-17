"""The QA Controller (ON-46, steps 3 to 8).

One decision, and the tests that matter are about the word *skips* in the
contracts' own sentence: "The QA Controller **skips the LLM** and returns
fallback: true with a message directing the employee to HR."

Returning a fallback is easy and proves very little. A controller that
asked the model anyway and then threw its answer away would pass any test
that only looked at the result - and would be a different system, one
that spends twenty seconds and a model call on every unanswerable
question and depends on the model to decline. So the provider used here
records every prompt it is given, and the central assertion is that it
was never asked at all.
"""

from __future__ import annotations

import logging

import pytest

from app.config import get_settings
from app.db.models import Document, Section, User
from app.services.embedding.provider import EmbeddingError, EmbeddingProvider
from app.services.llm.gateway import HR_FALLBACK_MESSAGE, LLMGateway, PromptSection
from app.services.llm.provider import LLMError, LLMProvider
from app.services.qa import Answer, QAController, to_prompt_sections
from app.services.qa import controller as qa
from app.services.retrieval import RetrievedSection

NORTH = [0.0, 1.0]
EAST = [1.0, 0.0]


class RecordingLLM(LLMProvider):
    """Answers, and remembers whether it was asked.

    `prompts` is the whole point of this file: the threshold is only doing
    its job if this list stays empty.
    """

    def __init__(self, output: str | None = None, fail: Exception | None = None) -> None:
        self.prompts: list[str] = []
        self.output = output
        self.fail = fail

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.fail is not None:
            raise self.fail
        if self.output is not None:
            return self.output
        ids = [line for line in prompt.splitlines() if line.startswith("[section:")]
        first = ids[0].split("]")[0].removeprefix("[section:") if ids else "0"
        return (
            '{"answer": "Twenty days.", "citations": '
            f'[{{"section_id": {first}, "heading": "Holiday"}}]}}'
        )


class FixedEmbedder(EmbeddingProvider):
    def __init__(self, vector: list[float]) -> None:
        self.vector = vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(self.vector) for _ in texts]


def _section_rows(session, collection, vectors: list[list[float]]) -> list[Section]:
    owner = User(
        email="hr@example.com",
        full_name="Jordan HR",
        password_hash="scrypt:not-a-real-hash",
        role="hr_administrator",
    )
    session.add(owner)
    session.flush()
    document = Document(
        filename="handbook.pdf",
        content_type="pdf",
        stored_path="backend/storage/documents/handbook.pdf",
        size_bytes=1024,
        uploaded_by=owner,
    )
    session.add(document)
    session.flush()

    rows = []
    for position, vector in enumerate(vectors):
        section = Section(
            document=document,
            position=position,
            heading=f"Heading {position}",
            text=f"Policy text {position}.",
        )
        session.add(section)
        session.flush()
        collection.upsert(
            ids=[str(section.id)],
            embeddings=[vector],
            metadatas=[{"document_id": document.id, "position": position}],
        )
        rows.append(section)
    session.commit()
    return rows


@pytest.fixture
def library(db_session, collection):
    """Two sections: one pointing north, one east."""
    return _section_rows(db_session, collection, [NORTH, EAST])


@pytest.fixture
def patched_retrieval(monkeypatch, collection):
    """Make the controller's `retrieve` use the fake collection.

    The controller calls `retrieve(question, session)` with no collection
    of its own, which is right - the Chat API should not be passing one
    around - so the fake is wired in where retrieval looks for it.
    """
    from app.services.retrieval import service as retrieval_service

    monkeypatch.setattr(retrieval_service, "get_collection", lambda: collection)


def controller_for(provider: LLMProvider, threshold: float) -> QAController:
    return QAController(gateway=LLMGateway(provider, timeout_seconds=5.0), threshold=threshold)


# --- the decision this component exists for ----------------------------


def test_below_the_threshold_the_model_is_never_asked(
    db_session, collection, library, patched_retrieval, monkeypatch
):
    """The one that matters.

    A question pointing east matches the east section exactly, so the
    score is 1.0 - and a threshold above that must stop it dead.
    """
    provider = RecordingLLM()
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.1))

    answer = controller_for(provider, threshold=0.5).ask("anything", db_session)

    assert answer.fallback is True
    assert provider.prompts == [], "the provider was asked despite the score being below threshold"


def test_below_the_threshold_the_employee_is_sent_to_hr(db_session, monkeypatch):
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.1))

    answer = controller_for(RecordingLLM(), threshold=0.5).ask("anything", db_session)

    assert answer.answer == HR_FALLBACK_MESSAGE
    assert answer.citations == []


def test_above_the_threshold_the_model_is_asked(db_session, monkeypatch):
    provider = RecordingLLM()
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.9))

    answer = controller_for(provider, threshold=0.5).ask("holiday", db_session)

    assert len(provider.prompts) == 1
    assert answer.fallback is False
    assert answer.answer == "Twenty days."


def test_a_score_exactly_on_the_threshold_is_good_enough(db_session, monkeypatch):
    """ "Below the threshold" is below it, so equal passes.

    Pinned because the difference between `<` and `<=` is invisible in
    every test that does not sit exactly on the line, and a threshold
    somebody tunes to a measured value is a threshold where the boundary
    gets hit.
    """
    provider = RecordingLLM()
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.5))

    answer = controller_for(provider, threshold=0.5).ask("holiday", db_session)

    assert answer.fallback is False
    assert len(provider.prompts) == 1


def test_a_score_a_hair_under_the_threshold_is_not(db_session, monkeypatch):
    provider = RecordingLLM()
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.4999))

    assert controller_for(provider, threshold=0.5).ask("holiday", db_session).fallback is True
    assert provider.prompts == []


def test_only_the_best_score_decides(db_session, monkeypatch):
    """Not the average, and not the worst.

    Four poor sections and one good one is the normal shape of a hit: the
    top-5 cut returns five whatever happens, so most results are padding.
    Judging on anything but the first would refuse almost everything.
    """
    provider = RecordingLLM()
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(scores=[0.9, 0.1, 0.05, 0.0, -0.2]))

    answer = controller_for(provider, threshold=0.5).ask("holiday", db_session)

    assert answer.fallback is False
    assert answer.best_score == pytest.approx(0.9)


def test_the_reason_records_the_score_and_the_threshold(db_session, monkeypatch):
    """So a tuning session can read the log rather than guess."""
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.123))

    answer = controller_for(RecordingLLM(), threshold=0.5).ask("anything", db_session)

    assert "0.123" in answer.reason
    assert "0.500" in answer.reason


def test_the_reason_is_never_part_of_what_an_employee_reads(db_session, monkeypatch):
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.1))

    answer = controller_for(RecordingLLM(), threshold=0.5).ask("anything", db_session)

    assert answer.reason not in answer.answer
    assert "threshold" not in answer.answer.lower()


def test_a_below_threshold_refusal_still_reports_what_it_saw(db_session, monkeypatch):
    """ "Found nothing" and "found five poor ones" are different refusals.

    ON-24 measures the fallback rate and has to tell them apart: the first
    means the handbook does not cover the subject, the second means it may
    well and retrieval could not find it. With `retrieved` zeroed they look
    identical in the log, which is how a retrieval problem gets filed as a
    content gap. Found by fault injection - every other test read
    `retrieved` on a path that answered.
    """
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(scores=[0.1, 0.05, 0.0]))

    answer = controller_for(RecordingLLM(), threshold=0.5).ask("anything", db_session)

    assert answer.fallback is True
    assert answer.retrieved == 3
    assert answer.best_score == pytest.approx(0.1)


# --- nothing retrieved at all -------------------------------------------


def test_nothing_retrieved_means_the_model_is_not_asked(db_session, monkeypatch):
    """An empty Vector Database, or a question that matched nothing.

    The Gateway refuses to build a prompt with no sections anyway, but
    reaching it would already have cost a round trip and would put the
    decision in the wrong component.
    """
    provider = RecordingLLM()
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(scores=[]))

    answer = controller_for(provider, threshold=0.5).ask("holiday", db_session)

    assert answer.fallback is True
    assert answer.retrieved == 0
    assert answer.best_score is None
    assert provider.prompts == []


def test_a_blank_question_does_not_reach_the_model(
    db_session, collection, library, patched_retrieval
):
    """Through the real retrieval path, which declines to embed it."""
    provider = RecordingLLM()

    answer = controller_for(provider, threshold=-1.0).ask("   ", db_session)

    assert answer.fallback is True
    assert provider.prompts == []


# --- a failure in the AI path -------------------------------------------


def test_an_embedding_failure_becomes_the_fallback_not_an_error(db_session, monkeypatch):
    """ "A failure in the AI path returns the HR fallback instead of an error."""

    def explode(*_args, **_kwargs):
        raise EmbeddingError("the Embedding API answered 429.")

    monkeypatch.setattr(qa, "retrieve", explode)

    answer = controller_for(RecordingLLM(), threshold=0.5).ask("holiday", db_session)

    assert answer.fallback is True
    assert answer.answer == HR_FALLBACK_MESSAGE


def test_a_vector_database_failure_becomes_the_fallback(db_session, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("the Vector Database is not answering")

    monkeypatch.setattr(qa, "retrieve", explode)

    assert controller_for(RecordingLLM(), threshold=0.5).ask("x", db_session).fallback is True


def test_a_retrieval_failure_says_so_in_the_reason(db_session, monkeypatch, caplog):
    """Unlike the other fallbacks, this one is somebody's to fix."""

    def explode(*_args, **_kwargs):
        raise EmbeddingError("the Embedding API answered 429.")

    monkeypatch.setattr(qa, "retrieve", explode)

    with caplog.at_level(logging.ERROR, logger="app.services.qa.controller"):
        answer = controller_for(RecordingLLM(), threshold=0.5).ask("holiday", db_session)

    assert "EmbeddingError" in answer.reason
    assert "429" in answer.reason
    assert "Traceback" in caplog.text


def test_a_provider_error_is_the_gateways_verdict_carried_through(db_session, monkeypatch):
    """Not re-decided here. Two components judging one thing is one too many."""
    provider = RecordingLLM(fail=LLMError("the provider is down"))
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.9))

    answer = controller_for(provider, threshold=0.5).ask("holiday", db_session)

    assert answer.fallback is True
    assert answer.answer == HR_FALLBACK_MESSAGE
    assert "the provider is down" in answer.reason
    assert len(provider.prompts) == 1, "the provider should have been asked, and failed"


def test_output_that_fails_the_json_check_becomes_the_fallback(db_session, monkeypatch):
    provider = RecordingLLM(output="I am afraid I cannot do that.")
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.9))

    answer = controller_for(provider, threshold=0.5).ask("holiday", db_session)

    assert answer.fallback is True
    assert "JSON" in answer.reason


def test_an_answer_citing_nothing_it_was_given_becomes_the_fallback(db_session, monkeypatch):
    """The second defence, and the one that catches what the threshold lets by."""
    provider = RecordingLLM(
        output='{"answer": "Thirty days.", "citations": [{"section_id": 9999}]}'
    )
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.9))

    answer = controller_for(provider, threshold=0.5).ask("holiday", db_session)

    assert answer.fallback is True


# --- what the Chat API gets to work with --------------------------------


def test_a_good_answer_carries_its_citations(db_session, monkeypatch):
    provider = RecordingLLM()
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.9))

    answer = controller_for(provider, threshold=0.5).ask("holiday", db_session)

    assert [citation.section_id for citation in answer.citations] == [1]
    assert answer.citations[0].document == "handbook.pdf"


def test_the_score_and_the_count_come_back_for_the_log(db_session, monkeypatch):
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(scores=[0.9, 0.8, 0.7]))

    answer = controller_for(RecordingLLM(), threshold=0.5).ask("holiday", db_session)

    assert answer.best_score == pytest.approx(0.9)
    assert answer.retrieved == 3


def test_the_score_is_reported_even_when_the_gateway_fell_back(db_session, monkeypatch):
    """ON-24 has to tell a below-threshold refusal from a model that broke."""
    provider = RecordingLLM(output="not json")
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.9))

    answer = controller_for(provider, threshold=0.5).ask("holiday", db_session)

    assert answer.fallback is True
    assert answer.best_score == pytest.approx(0.9)


def test_an_answer_cannot_be_edited_after_the_fact():
    from dataclasses import FrozenInstanceError

    answer = Answer(answer="Twenty days.")

    with pytest.raises(FrozenInstanceError):
        answer.answer = "Forty days."  # type: ignore[misc]


# --- the join between the two neighbours --------------------------------


def test_retrieved_sections_become_prompt_sections_intact():
    retrieved = [
        RetrievedSection(
            section_id=7,
            document_id=3,
            document="benefits.pdf",
            heading="Dental",
            position=2,
            text="Dental is covered.",
            score=0.8,
            distance=0.2,
        )
    ]

    assert to_prompt_sections(retrieved) == [
        PromptSection(
            section_id=7, heading="Dental", text="Dental is covered.", document="benefits.pdf"
        )
    ]


def test_the_order_retrieval_chose_is_the_order_the_prompt_gets(db_session, monkeypatch):
    """The ranking ON-43 worked to preserve must not be lost on the way in."""
    provider = RecordingLLM()
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(scores=[0.9, 0.8, 0.7]))

    controller_for(provider, threshold=0.5).ask("holiday", db_session)

    prompt = provider.prompts[0]
    positions = [prompt.index(f"[section:{identifier}]") for identifier in (1, 2, 3)]
    assert positions == sorted(positions)


def test_the_prompt_carries_the_retrieved_text_and_the_question(db_session, monkeypatch):
    provider = RecordingLLM()
    monkeypatch.setattr(qa, "retrieve", _retrieval_returning(score=0.9))

    controller_for(provider, threshold=0.5).ask("How much holiday?", db_session)

    assert "Policy text 0." in provider.prompts[0]
    assert "How much holiday?" in provider.prompts[0]


# --- the whole thing, over the real retrieval path ----------------------


def test_end_to_end_a_matching_question_is_answered(
    db_session, collection, library, patched_retrieval, monkeypatch
):
    """Real Retrieval Service, real Gateway, fake stores and provider."""
    provider = RecordingLLM()
    monkeypatch.setattr(
        "app.services.retrieval.service.embed_question",
        lambda question, provider=None, settings=None: NORTH,
    )

    answer = controller_for(provider, threshold=0.5).ask("holiday", db_session)

    assert answer.fallback is False
    assert answer.best_score == pytest.approx(1.0)
    assert len(provider.prompts) == 1


def test_end_to_end_an_unrelated_question_never_reaches_the_model(
    db_session, collection, library, patched_retrieval, monkeypatch
):
    """North and east are perpendicular, so the best score is 0.0."""
    provider = RecordingLLM()
    monkeypatch.setattr(
        "app.services.retrieval.service.embed_question",
        lambda question, provider=None, settings=None: [-1.0, 0.0],
    )

    answer = controller_for(provider, threshold=0.5).ask("the weather", db_session)

    assert answer.fallback is True
    assert provider.prompts == []
    assert answer.best_score == pytest.approx(0.0)


# --- configuration -------------------------------------------------------


def test_the_threshold_comes_from_configuration(monkeypatch):
    monkeypatch.setenv("RELEVANCE_THRESHOLD", "0.75")
    get_settings.cache_clear()
    try:
        controller = QAController(gateway=LLMGateway(RecordingLLM()))
    finally:
        get_settings.cache_clear()

    assert controller.threshold == 0.75


def test_the_shipped_threshold_is_the_measured_one():
    """The literal, so a rename cannot move it.

    0.22 is what best separated the evaluation set's answerable questions
    from its unanswerable ones against the mock embedder. It is
    provisional by ON-46's own wording and provider-specific by nature -
    see TD-30.
    """
    get_settings.cache_clear()
    try:
        assert get_settings().relevance_threshold == 0.22
    finally:
        get_settings.cache_clear()


def test_a_threshold_no_score_could_ever_reach_is_refused(monkeypatch):
    """Above 1.0 every employee gets the fallback forever and nothing says why."""
    from pydantic import ValidationError

    from app.config import Settings

    monkeypatch.setenv("RELEVANCE_THRESHOLD", "1.5")
    with pytest.raises(ValidationError):
        Settings()


def test_a_threshold_below_minus_one_is_refused(monkeypatch):
    from pydantic import ValidationError

    from app.config import Settings

    monkeypatch.setenv("RELEVANCE_THRESHOLD", "-2")
    with pytest.raises(ValidationError):
        Settings()


def test_the_controller_builds_its_own_gateway_when_not_given_one():
    """The Chat API asks for a controller, not for a provider and a gateway."""
    controller = QAController()

    assert isinstance(controller.gateway, LLMGateway)
    assert controller.gateway.timeout_seconds == 20.0


# --- helpers --------------------------------------------------------------


def _retrieval_returning(score: float | None = None, scores: list[float] | None = None):
    """A stand-in for `retrieve` that returns sections at chosen scores.

    The real Retrieval Service has its own tests; what this file is about
    is what the controller does with what it gets back, and the scores
    have to be set exactly to put one either side of a threshold.
    """
    values = scores if scores is not None else [score if score is not None else 0.0]

    def fake(_question, _session, **_kwargs):
        return [
            RetrievedSection(
                section_id=index + 1,
                document_id=1,
                document="handbook.pdf",
                heading=f"Heading {index}",
                position=index,
                text=f"Policy text {index}.",
                score=value,
                distance=1.0 - value,
            )
            for index, value in enumerate(values)
        ]

    return fake
