"""The LLMProvider interface and the Mock LLM (ON-44).

The contracts fix one method signature in the whole design -
`generate(prompt)` - so the first thing tested here is that it is still
that, with nothing added. The rest is the mock behaving like the three
kinds of broken provider the contracts name, because the LLM Gateway
(ON-45) cannot be tested against conditions nothing can produce.
"""

import inspect
import json
import time

import pytest

from app.config import Settings, get_settings
from app.services.llm import PROVIDERS, LLMError, LLMProvider, MockLLM, get_provider
from app.services.llm.mock import NO_CONTEXT_ANSWER

PROMPT = "Answer from the following.\n\n[section:42] 5.1 ELIGIBILITY\nText.\n"


# --- the interface the contracts fix ----------------------------------


def test_generate_takes_a_prompt_and_nothing_else():
    """The one signature the design fixes.

    Adding a temperature or a model name here would be a reason the QA
    Controller has to change when the provider does, which is the single
    thing this interface exists to prevent.
    """
    parameters = list(inspect.signature(LLMProvider.generate).parameters)

    assert parameters == ["self", "prompt"]


def test_generate_returns_a_string():
    """Not parsed JSON. Whether the output is usable is the Gateway's
    judgement, and a provider that parsed its own output would have to
    decide what to do with a malformed answer."""
    assert inspect.signature(LLMProvider.generate).return_annotation == "str"
    assert isinstance(MockLLM().generate(PROMPT), str)


def test_a_provider_without_generate_cannot_be_built():
    """An abstract base class rather than a Protocol, so forgetting the
    method fails when somebody builds the class - not later, when an
    employee asks a question."""

    class Forgetful(LLMProvider):
        pass

    with pytest.raises(TypeError):
        Forgetful()


def test_the_mock_is_a_provider():
    assert isinstance(MockLLM(), LLMProvider)


def test_a_provider_knows_its_own_name():
    assert MockLLM().name == "mock"


# --- answering ---------------------------------------------------------


def test_an_answer_is_json_with_citations():
    """The contracts: "the answer comes back as JSON with citations"."""
    answer = json.loads(MockLLM().generate(PROMPT))

    assert set(answer) == {"answer", "citations"}
    assert answer["answer"]
    assert answer["citations"] == [{"section_id": 42, "heading": "5.1 ELIGIBILITY"}]


def test_it_cites_every_section_the_prompt_carried():
    prompt = "\n".join(
        [
            "[section:1] 1.1 WELCOME",
            "Text.",
            "[section:7] 5.3 RETIREMENT SAVINGS",
            "More text.",
        ]
    )

    citations = json.loads(MockLLM().generate(prompt))["citations"]

    assert [citation["section_id"] for citation in citations] == [1, 7]


def test_a_section_with_no_heading_still_gets_a_citation():
    """A citation with no title is better than a citation that is missing."""
    citations = json.loads(MockLLM().generate("[section:9]\nText."))["citations"]

    assert citations == [{"section_id": 9, "heading": "Section 9"}]


def test_a_prompt_with_no_sections_produces_no_citations():
    """If ON-45 builds prompts a different way the mock finds no markers,
    and that must still be valid output rather than a crash."""
    answer = json.loads(MockLLM().generate("Just a question, no context."))

    assert answer["citations"] == []
    assert answer["answer"] == NO_CONTEXT_ANSWER


def test_the_answer_never_pretends_to_be_a_real_one():
    """A fake answer that reads like a real HR answer is one somebody
    eventually screenshots into a report."""
    for prompt in (PROMPT, "no context here"):
        answer = json.loads(MockLLM().generate(prompt))["answer"]

        assert "Mock LLM" in answer


def test_it_remembers_what_it_was_asked():
    """So a test of the Gateway can assert the prompt was limited to the
    retrieved text, which only an inspectable provider can show."""
    mock = MockLLM()

    mock.generate("first")
    mock.generate("second")

    assert mock.prompts == ["first", "second"]


def test_the_same_prompt_answers_the_same_way_twice():
    """A mock that varied would make every test of the answer path flaky."""
    mock = MockLLM()

    assert mock.generate(PROMPT) == mock.generate(PROMPT)


# --- the three broken providers the contracts name ---------------------


def test_a_provider_that_errors_raises_llm_error():
    with pytest.raises(LLMError, match="the provider is down"):
        MockLLM(fail_with="the provider is down").generate(PROMPT)


def test_a_provider_that_returns_something_other_than_json():
    """The Gateway checks the output; this is what it has to catch."""
    broken = MockLLM(raw_response="I'm afraid I can't do that.")

    output = broken.generate(PROMPT)

    assert output == "I'm afraid I can't do that."
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)


def test_a_provider_that_takes_too_long():
    """A real sleep, because what ON-45 needs to test is a provider that
    does not come back in time - a fake clock would not exercise whatever
    it uses to give up waiting."""
    started = time.monotonic()

    MockLLM(delay_seconds=0.05).generate(PROMPT)

    assert time.monotonic() - started >= 0.05


def test_an_error_is_raised_before_any_answer_is_built():
    """Otherwise a failing provider still looks like it did some work."""
    mock = MockLLM(fail_with="down", raw_response='{"answer": "x"}')

    with pytest.raises(LLMError):
        mock.generate(PROMPT)


# --- choosing a provider ----------------------------------------------


def test_the_mock_is_the_default(monkeypatch):
    """CI and teammates without the model must be able to run the system."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    get_settings.cache_clear()
    try:
        assert Settings(_env_file=None).llm_provider == "mock"
        assert get_provider(Settings(_env_file=None)).name == "mock"
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("spelling", ["mock", "MOCK", " Mock "])
def test_the_name_is_read_forgivingly(spelling):
    assert get_provider(Settings(llm_provider=spelling)).name == "mock"


def test_an_unknown_provider_is_an_error_rather_than_a_quiet_fallback():
    """Falling back would mean a deployment that believes it is using a
    real model, answers every question with "this came from the Mock LLM",
    and says so nowhere anybody is looking."""
    with pytest.raises(RuntimeError, match="not one of"):
        get_provider(Settings(llm_provider="gpt-9"))


def test_the_real_provider_is_not_selectable_yet():
    """ON-18's to add. A name that resolves to nothing is better than one
    that resolves to a stub nobody notices."""
    assert "real" not in PROVIDERS

    with pytest.raises(RuntimeError, match="ON-18"):
        get_provider(Settings(llm_provider="real"))


def test_every_registered_provider_implements_the_interface():
    for name, provider in PROVIDERS.items():
        assert issubclass(provider, LLMProvider), name
        # And can be built with no arguments, because that is how
        # get_provider builds it.
        assert isinstance(provider(), LLMProvider)
