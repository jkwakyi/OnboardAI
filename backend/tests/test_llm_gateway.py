"""The LLM Gateway (ON-45).

Three jobs, all of them about not trusting the model: the prompt carries
only the retrieved text, the wait is bounded, and the output is checked.

The contracts name four conditions that produce the HR fallback — below the
relevance threshold, a timeout, a provider error, and output that fails the
JSON check. Three of those are this component's, and each has a test that
drives the real path rather than a stubbed one, because the Mock LLM can
produce all three.
"""

import json
import time

import pytest

from app.services.llm.gateway import (
    HR_FALLBACK_MESSAGE,
    MAX_QUESTION_CHARACTERS,
    TIMEOUT_SECONDS,
    GatewayResult,
    LLMGateway,
    PromptSection,
)
from app.services.llm.mock import MockLLM
from app.services.llm.provider import LLMProvider

QUESTION = "How long do I have to enrol in the medical plan?"

SECTIONS = [
    PromptSection(
        section_id=11,
        heading="5.1 ELIGIBILITY AND ENROLMENT",
        text="You have 30 days from your start date to enrol.",
        document="05-benefits-and-wellbeing.pdf",
    ),
    PromptSection(
        section_id=12,
        heading="5.2 MEDICAL AND DENTAL COVER",
        text="Two medical plans are offered, a Standard plan and a High Deductible plan.",
        document="05-benefits-and-wellbeing.pdf",
    ),
]


def gateway(provider: LLMProvider | None = None, **options) -> LLMGateway:
    options.setdefault("timeout_seconds", 1.0)
    return LLMGateway(provider or MockLLM(), **options)


def answering(payload: object) -> MockLLM:
    """A provider that returns exactly this, as JSON."""
    return MockLLM(raw_response=json.dumps(payload))


# --- the contractual constant -----------------------------------------


def test_the_timeout_is_the_twenty_seconds_the_contracts_fix():
    """A constant, not a setting. A deployment that quietly set this to 120
    would be running a different design."""
    assert TIMEOUT_SECONDS == 20.0
    assert LLMGateway(MockLLM()).timeout_seconds == 20.0


# --- the prompt carries the retrieved text and nothing else -----------


def test_the_prompt_contains_every_retrieved_section():
    prompt = gateway().build_prompt(QUESTION, SECTIONS)

    for section in SECTIONS:
        assert section.text in prompt
        assert str(section.section_id) in prompt
        assert section.heading in prompt


def test_the_prompt_contains_the_question():
    assert QUESTION in gateway().build_prompt(QUESTION, SECTIONS)


def test_the_prompt_contains_no_other_document_text():
    """ "The LLM Gateway limits the prompt to the retrieved text" - the
    contracts. A model given no other material has nothing else to answer
    from."""
    prompt = gateway().build_prompt(QUESTION, SECTIONS)

    assert "401(k)" not in prompt
    assert "RETIREMENT" not in prompt


def test_a_section_with_no_heading_is_still_labelled():
    """Every section needs a marker, or the model cannot cite it at all."""
    prompt = gateway().build_prompt(
        QUESTION, [PromptSection(section_id=9, heading=None, text="Some policy text.")]
    )

    assert "[section:9]" in prompt
    assert "Section 9" in prompt


def test_an_enormous_question_is_cut_down():
    """Otherwise one paste pushes the retrieved sections out of the
    model's context window.

    Asserted as a run of x's rather than a count of them: the
    instructions contain the word "text", so counting every x in the
    prompt counts that one too and the test fails by exactly one for a
    reason that has nothing to do with the question.
    """
    prompt = gateway().build_prompt("x" * 50_000, SECTIONS)

    assert "x" * MAX_QUESTION_CHARACTERS in prompt
    assert "x" * (MAX_QUESTION_CHARACTERS + 1) not in prompt
    # And the sections are still in there, which is the point.
    assert SECTIONS[0].text in prompt


def test_the_question_is_marked_as_a_question():
    """The last QUESTION, not the first: the instructions mention the
    marker by name when they tell the model what is inside it."""
    prompt = gateway().build_prompt(QUESTION, SECTIONS)

    assert prompt.rindex("QUESTION") > prompt.index("SECTIONS")
    assert prompt.rstrip().endswith(QUESTION)


def test_the_provider_is_given_exactly_that_prompt():
    """Checked through the mock's record of what it was asked, because an
    assertion about the prompt is worth little if something else is sent."""
    mock = MockLLM()

    gateway(mock).answer(QUESTION, SECTIONS)

    assert mock.prompts == [gateway(mock).build_prompt(QUESTION, SECTIONS)]


# --- answering --------------------------------------------------------


def test_a_good_answer_comes_back_with_its_citations():
    result = gateway().answer(QUESTION, SECTIONS)

    assert result.fallback is False
    assert result.answer
    assert [citation.section_id for citation in result.citations] == [11, 12]


def test_a_citation_is_labelled_from_the_retrieved_section():
    """Not from the model. A citation cannot be mislabelled even when the
    id is right."""
    provider = answering(
        {"answer": "30 days.", "citations": [{"section_id": 11, "heading": "Something else"}]}
    )

    citation = gateway(provider).answer(QUESTION, SECTIONS).citations[0]

    assert citation.heading == "5.1 ELIGIBILITY AND ENROLMENT"
    assert citation.document == "05-benefits-and-wellbeing.pdf"


def test_a_citation_the_model_invented_is_dropped():
    """The strongest thing in the component. An employee can follow a
    citation to the paragraph it came from; a citation to a section that
    was never retrieved is one nobody can follow."""
    provider = answering(
        {
            "answer": "30 days.",
            "citations": [{"section_id": 11}, {"section_id": 9999, "heading": "Invented"}],
        }
    )

    result = gateway(provider).answer(QUESTION, SECTIONS)

    assert [citation.section_id for citation in result.citations] == [11]
    assert result.fallback is False


def test_an_answer_whose_citations_are_all_invented_is_a_fallback():
    """An answer nobody can check is the invented policy this design
    exists to prevent."""
    provider = answering({"answer": "Ten years.", "citations": [{"section_id": 9999}]})

    result = gateway(provider).answer(QUESTION, SECTIONS)

    assert result.fallback is True
    assert result.answer == HR_FALLBACK_MESSAGE


def test_the_same_section_cited_twice_is_one_citation():
    provider = answering(
        {"answer": "30 days.", "citations": [{"section_id": 11}, {"section_id": 11}]}
    )

    assert len(gateway(provider).answer(QUESTION, SECTIONS).citations) == 1


@pytest.mark.parametrize(
    "citations",
    [
        [{"section_id": "11"}],
        [{"section_id": 11.0}],
    ],
)
def test_a_section_id_that_is_not_quite_an_integer_still_matches(citations):
    """Models are careless with types, and this is not the place to be
    strict about it: the id resolves to a section that was retrieved."""
    provider = answering({"answer": "30 days.", "citations": citations})

    assert gateway(provider).answer(QUESTION, SECTIONS).citations[0].section_id == 11


@pytest.mark.parametrize(
    "citations",
    [
        ["section 11"],
        [{"section_id": None}],
        [{"section_id": "the first one"}],
        [{"heading": "5.1 ELIGIBILITY AND ENROLMENT"}],
        [None],
    ],
)
def test_a_citation_that_names_nothing_usable_is_dropped(citations):
    provider = answering({"answer": "30 days.", "citations": citations})

    result = gateway(provider).answer(QUESTION, SECTIONS)

    assert result.fallback is True


# --- the three failures the contracts name ----------------------------


def test_a_timeout_is_the_hr_fallback_not_an_error():
    slow = MockLLM(delay_seconds=0.3)

    result = gateway(slow, timeout_seconds=0.05).answer(QUESTION, SECTIONS)

    assert result.fallback is True
    assert result.answer == HR_FALLBACK_MESSAGE
    assert "did not answer within" in (result.reason or "")


def test_the_gateway_stops_waiting_rather_than_waiting_it_out():
    """The limit is only a limit if it returns before the provider does."""
    slow = MockLLM(delay_seconds=2.0)
    started = time.monotonic()

    gateway(slow, timeout_seconds=0.1).answer(QUESTION, SECTIONS)

    assert time.monotonic() - started < 1.0


def test_a_provider_error_is_the_hr_fallback():
    result = gateway(MockLLM(fail_with="the provider is down")).answer(QUESTION, SECTIONS)

    assert result.fallback is True
    assert result.answer == HR_FALLBACK_MESSAGE
    assert "down" in (result.reason or "")


def test_something_unexpected_from_a_provider_is_still_the_hr_fallback():
    """An employee cannot be shown a stack trace by a model having a bad
    day, whatever the provider does."""

    class Broken(LLMProvider):
        def generate(self, prompt: str) -> str:
            raise ZeroDivisionError("not even an LLMError")

    result = gateway(Broken()).answer(QUESTION, SECTIONS)

    assert result.fallback is True
    assert result.answer == HR_FALLBACK_MESSAGE
    assert "ZeroDivisionError" in (result.reason or "")


@pytest.mark.parametrize(
    "output",
    [
        "I'm afraid I can't do that.",
        "",
        "   ",
        "{",
        '{"answer": "30 days", "citations": [}',
        "null",
        "[]",
        '"just a string"',
        "42",
    ],
)
def test_output_that_is_not_a_json_object_is_the_hr_fallback(output):
    result = gateway(MockLLM(raw_response=output)).answer(QUESTION, SECTIONS)

    assert result.fallback is True
    assert result.answer == HR_FALLBACK_MESSAGE


@pytest.mark.parametrize(
    "payload",
    [
        {"citations": [{"section_id": 11}]},
        {"answer": "", "citations": [{"section_id": 11}]},
        {"answer": "   ", "citations": [{"section_id": 11}]},
        {"answer": 42, "citations": [{"section_id": 11}]},
        {"answer": None, "citations": [{"section_id": 11}]},
        {"answer": "30 days."},
        {"answer": "30 days.", "citations": "section 11"},
        {"answer": "30 days.", "citations": {}},
        {"answer": "30 days.", "citations": []},
    ],
)
def test_json_missing_what_an_answer_needs_is_the_hr_fallback(payload):
    result = gateway(answering(payload)).answer(QUESTION, SECTIONS)

    assert result.fallback is True
    assert result.answer == HR_FALLBACK_MESSAGE


def test_extra_fields_in_the_output_are_ignored_rather_than_refused():
    """Models add things. A usable answer should not be thrown away because
    it came with a confidence score nobody asked for."""
    provider = answering(
        {"answer": "30 days.", "citations": [{"section_id": 11}], "confidence": 0.9}
    )

    assert gateway(provider).answer(QUESTION, SECTIONS).fallback is False


# --- the fallback itself ----------------------------------------------


def test_every_fallback_says_the_same_thing_to_the_employee():
    """However the AI path failed. The reason is for the log and for
    ON-24's measurements, not for whoever asked the question."""
    failures = [
        MockLLM(fail_with="down"),
        MockLLM(raw_response="not json"),
        MockLLM(delay_seconds=0.3),
        answering({"answer": "x", "citations": [{"section_id": 9999}]}),
    ]

    answers = {
        gateway(provider, timeout_seconds=0.05).answer(QUESTION, SECTIONS).answer
        for provider in failures
    }

    assert answers == {HR_FALLBACK_MESSAGE}


def test_every_fallback_carries_a_different_reason_for_the_log():
    """Or nobody can tell a flaky provider from a bad prompt."""
    reasons = {
        gateway(MockLLM(fail_with="down")).answer(QUESTION, SECTIONS).reason,
        gateway(MockLLM(raw_response="not json")).answer(QUESTION, SECTIONS).reason,
        gateway(answering({"answer": "x", "citations": []})).answer(QUESTION, SECTIONS).reason,
    }

    assert len(reasons) == 3
    assert all(reason for reason in reasons)


def test_the_fallback_message_directs_the_employee_to_hr():
    """The contracts' words: "a message directing the employee to HR"."""
    assert "HR" in HR_FALLBACK_MESSAGE


def test_no_sections_is_a_fallback_without_asking_the_model():
    """The QA Controller is meant to skip the LLM below the relevance
    threshold. Reaching here with nothing retrieved means it did not, and
    asking a model to answer from no material is how an invented policy
    gets written."""
    mock = MockLLM()

    result = gateway(mock).answer(QUESTION, [])

    assert result.fallback is True
    assert mock.prompts == [], "the provider was asked despite having nothing to answer from"


def test_the_gateway_never_raises_whatever_the_provider_does():
    for provider in (
        MockLLM(fail_with="down"),
        MockLLM(raw_response="not json"),
        MockLLM(delay_seconds=0.2),
    ):
        result = gateway(provider, timeout_seconds=0.05).answer(QUESTION, SECTIONS)

        assert isinstance(result, GatewayResult)


# --- the mock and the gateway agree on the marker ---------------------


def test_the_mock_can_read_the_markers_the_gateway_writes():
    """ON-44 guessed at the prompt format and said so. This is the test
    that keeps the two in step, and the reason the guess was cheap."""
    mock = MockLLM()

    result = gateway(mock).answer(QUESTION, SECTIONS)

    assert result.fallback is False
    assert [citation.section_id for citation in result.citations] == [11, 12]
    assert [citation.heading for citation in result.citations] == [
        "5.1 ELIGIBILITY AND ENROLMENT",
        "5.2 MEDICAL AND DENTAL COVER",
    ]
