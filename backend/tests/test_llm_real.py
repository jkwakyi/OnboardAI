"""The Real LLM Client (ON-18).

Every test injects the transport, so the suite needs no GPU, no 5 GB of
weights and no Ollama: it passes in CI, which has none of those.

What is actually being checked is that the client stays a *provider* and
does not start making the Gateway's decisions. It must hand back whatever
the model said, including output that is plainly not the JSON the prompt
asked for, because "the LLM output fails the JSON check" is a condition
the contracts give to the Gateway. A client that quietly fixed up bad
output would be the thing that let an invented policy through.
"""

import io
import json
import urllib.error
import urllib.request

import pytest

from app.config import GATEWAY_TIMEOUT_SECONDS, Settings
from app.services.llm.gateway import TIMEOUT_SECONDS, LLMGateway, PromptSection
from app.services.llm.provider import LLMError, LLMProvider
from app.services.llm.real import (
    MAX_ANSWER_TOKENS,
    TEMPERATURE,
    THINK,
    RealLLMClient,
)

URL = "http://127.0.0.1:11434/api/generate"
PROMPT = "Answer from the following.\n\n[section:42] 5.1 ELIGIBILITY\nText.\n"
ANSWER = '{"answer": "Fifteen days.", "citations": [{"section_id": 42}]}'


def settings_for(**overrides) -> Settings:
    base = {
        "llm_provider": "real",
        "llm_api_url": URL,
        "llm_model": "qwen3:8b",
        "llm_keep_alive": "30m",
        "llm_timeout_seconds": 30.0,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


class Recorder:
    """A transport that records what it was given and replies as told."""

    def __init__(self, replies=None):
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []
        self.replies = replies

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.replies is not None:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return json.dumps({"response": ANSWER, "done": True}).encode("utf-8")

    @property
    def bodies(self) -> list[dict]:
        return [json.loads(request.data) for request in self.requests]


def client_with(transport, **overrides) -> RealLLMClient:
    return RealLLMClient(settings_for(**overrides), send=transport)


def replying(body) -> Recorder:
    """A transport that answers once with `body`."""
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    if isinstance(body, str):
        body = body.encode("utf-8")
    return Recorder(replies=[body])


def http_error(code: int, body: str = "{}") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(URL, code, "refused", {}, io.BytesIO(body.encode()))


# --- it is a provider, and only a provider ----------------------------


def test_it_implements_the_interface():
    assert isinstance(client_with(Recorder()), LLMProvider)


def test_building_one_asks_the_model_nothing():
    """A teammate with LLM_PROVIDER=real and nothing running should find
    out when they ask a question, not when they start the backend - and
    the backend should still start."""
    sent = Recorder()

    RealLLMClient(settings_for(), send=sent)

    assert sent.requests == []


def test_the_name_says_which_model_answered():
    assert client_with(Recorder(), llm_model="mistral:7b").name == "real (mistral:7b)"


# --- the request ------------------------------------------------------


def test_it_posts_to_the_configured_url():
    sent = Recorder()
    client_with(sent).generate(PROMPT)

    assert sent.requests[0].full_url == URL
    assert sent.requests[0].method == "POST"


def test_it_sends_the_prompt_unchanged_and_the_configured_model():
    sent = Recorder()
    client_with(sent).generate(PROMPT)

    assert sent.bodies[0]["prompt"] == PROMPT
    assert sent.bodies[0]["model"] == "qwen3:8b"


def test_a_real_sized_prompt_arrives_whole():
    """`PROMPT` above is 60 characters, and a client that truncated at any
    sensible length would still pass the test before this one. A real
    prompt - the instructions, five retrieved sections and the question -
    measured about 2,900 characters, and losing its tail would drop the
    sections the answer has to cite.
    """
    section = "[section:{n}] 4.{n} A HEADING\n" + ("policy text. " * 40)
    long_prompt = "\n\n".join(section.format(n=n) for n in range(1, 6))
    assert len(long_prompt) > 2500, "the fixture stopped making this test meaningful"

    sent = Recorder()
    client_with(sent).generate(long_prompt)

    assert sent.bodies[0]["prompt"] == long_prompt


def test_it_asks_the_model_to_answer_in_json():
    """The Gateway's prompt asks for JSON; this makes the model constrain
    its output to JSON rather than hope."""
    sent = Recorder()
    client_with(sent).generate(PROMPT)

    assert sent.bodies[0]["format"] == "json"


def test_it_turns_reasoning_off():
    """Measured: the same question took 18.6 seconds with qwen3 thinking
    and 4.0 without, for the same answer and the same citation. The
    Gateway allows 20, so thinking on spends most of the budget producing
    text the JSON check throws away."""
    sent = Recorder()
    client_with(sent).generate(PROMPT)

    assert THINK is False
    assert sent.bodies[0]["think"] is False


def test_it_asks_for_one_answer_rather_than_a_sample():
    sent = Recorder()
    client_with(sent).generate(PROMPT)

    assert sent.bodies[0]["options"]["temperature"] == TEMPERATURE == 0.0


def test_it_caps_how_long_an_answer_may_run():
    """The 20 seconds are spent almost entirely generating tokens, so this
    is the number that decides whether a long-winded answer times out.

    The shipped number is asserted, not just that the constant reaches the
    request: `num_predict == MAX_ANSWER_TOKENS` stays true however far the
    constant moves, which is a test that cannot fail. qwen3 generated 87
    tokens for the longest answer measured and roughly 90 tokens per
    second with reasoning off, so 400 is a wide margin inside 20 seconds
    and 4,000 is not. Moving this needs a measurement, not an opinion.
    """
    assert MAX_ANSWER_TOKENS == 400

    sent = Recorder()
    client_with(sent).generate(PROMPT)

    assert sent.bodies[0]["options"]["num_predict"] == MAX_ANSWER_TOKENS


def test_it_keeps_the_model_loaded_between_questions():
    """A cold load measured 56 seconds, which the Gateway would not wait
    through - so an unloaded model means the HR fallback (TD-36)."""
    sent = Recorder()
    client_with(sent, llm_keep_alive="1h").generate(PROMPT)

    assert sent.bodies[0]["keep_alive"] == "1h"


def test_it_does_not_stream():
    """The Gateway's `generate` is one blocking call returning one string.
    A streamed reply arrives as a run of JSON objects, which would parse
    as the first token and nothing else."""
    sent = Recorder()
    client_with(sent).generate(PROMPT)

    assert sent.bodies[0]["stream"] is False


def test_no_credential_is_sent_anywhere():
    """The model is local. There is no key, and a header that looked like
    one would be a thing somebody later tries to fill in."""
    sent = Recorder()
    client_with(sent).generate(PROMPT)

    headers = {name.lower() for name in sent.requests[0].headers}
    assert "authorization" not in headers
    assert "api-key" not in headers
    assert "key" not in json.dumps(sent.bodies[0]).lower()


# --- the wait ---------------------------------------------------------


def test_the_socket_timeout_is_the_configured_one():
    sent = Recorder()
    client_with(sent, llm_timeout_seconds=42.0).generate(PROMPT)

    assert sent.timeouts[0] == 42.0


def test_the_socket_timeout_must_outlast_the_gateways():
    """Shorter, and this becomes the timeout: every slow answer would be
    reported as a provider error rather than a timeout. The employee sees
    the same fallback, but the log and ON-24's measurements would both be
    wrong about which happened."""
    with pytest.raises(ValueError, match="not longer than"):
        settings_for(llm_timeout_seconds=TIMEOUT_SECONDS)

    with pytest.raises(ValueError, match="not longer than"):
        settings_for(llm_timeout_seconds=5.0)


def test_the_configs_copy_of_the_gateway_limit_is_still_right():
    """`config.py` cannot import the LLM package - the package reads it -
    so the 20 seconds are written down twice. This is the thing that
    notices if one of them moves."""
    assert GATEWAY_TIMEOUT_SECONDS == TIMEOUT_SECONDS


# --- what comes back --------------------------------------------------


def test_it_returns_the_models_output():
    assert client_with(Recorder()).generate(PROMPT) == ANSWER


def test_output_that_is_not_json_comes_back_untouched():
    """The single most important test in this file. Whether the output is
    usable is the Gateway's judgement - a client that decided for itself
    would have to choose what to do with a bad answer, and the contracts
    already say: the HR fallback."""
    rambling = "Sure! Here's what I found:\n\nYou get 15 days."

    returned = client_with(replying({"response": rambling})).generate(PROMPT)

    assert returned == rambling


def test_json_that_is_the_wrong_shape_comes_back_untouched():
    wrong = '{"reply": "Fifteen days."}'

    assert client_with(replying({"response": wrong})).generate(PROMPT) == wrong


def test_surrounding_whitespace_is_kept():
    """Trimming is the Gateway's, and `json.loads` does not care. Doing it
    here would be this client having an opinion about output."""
    padded = f"  {ANSWER}\n"

    assert client_with(replying({"response": padded})).generate(PROMPT) == padded


# --- a provider that cannot answer ------------------------------------


def test_a_model_server_that_is_not_running():
    sent = Recorder(replies=[urllib.error.URLError("connection refused")])

    with pytest.raises(LLMError, match="could not reach the local model"):
        client_with(sent).generate(PROMPT)


def test_the_refusal_names_the_url_that_was_tried():
    """So a teammate reading the log knows whether it is the wrong port or
    nothing running at all."""
    sent = Recorder(replies=[urllib.error.URLError("connection refused")])

    with pytest.raises(LLMError, match=URL):
        client_with(sent).generate(PROMPT)


def test_a_model_that_was_never_pulled():
    """Ollama answers 404 for a model it does not have, which is the
    mistake a teammate is most likely to make."""
    sent = Recorder(replies=[http_error(404, '{"error": "model not found"}')])

    with pytest.raises(LLMError, match="qwen3:8b") as refusal:
        client_with(sent).generate(PROMPT)

    assert "not available" in str(refusal.value)
    assert "model not found" in str(refusal.value)


def test_another_http_refusal_reports_its_status():
    sent = Recorder(replies=[http_error(500, '{"error": "out of memory"}')])

    with pytest.raises(LLMError, match="500") as refusal:
        client_with(sent).generate(PROMPT)

    assert "out of memory" in str(refusal.value)


def test_an_http_refusal_with_an_unreadable_body_still_raises():
    sent = Recorder(replies=[http_error(503, "<html>gateway</html>")])

    with pytest.raises(LLMError, match="503"):
        client_with(sent).generate(PROMPT)


def test_a_model_that_does_not_answer_in_time():
    sent = Recorder(replies=[TimeoutError()])

    with pytest.raises(LLMError, match="within 30.0 seconds"):
        client_with(sent).generate(PROMPT)


def test_a_reply_that_is_not_json():
    sent = Recorder(replies=[b"<html>not ollama</html>"])

    with pytest.raises(LLMError, match="not JSON"):
        client_with(sent).generate(PROMPT)


def test_a_reply_that_is_json_but_not_an_object():
    with pytest.raises(LLMError, match="not an object"):
        client_with(replying([1, 2, 3])).generate(PROMPT)


def test_a_reply_with_no_response_field():
    with pytest.raises(LLMError, match="no 'response'"):
        client_with(replying({"done": True})).generate(PROMPT)


def test_a_response_that_is_not_a_string():
    with pytest.raises(LLMError, match="not a string"):
        client_with(replying({"response": {"answer": "hi"}})).generate(PROMPT)


def test_an_empty_answer_is_a_failure_rather_than_an_answer():
    """Passed on, the Gateway would fall back saying the output was not
    valid JSON - which points at the model's wording rather than at the
    model having said nothing at all."""
    with pytest.raises(LLMError, match="empty"):
        client_with(replying({"response": "   \n "})).generate(PROMPT)


# --- through the Gateway, which is the only way it is used ------------


def test_the_gateway_turns_a_real_answer_into_citations():
    sections = [PromptSection(section_id=42, heading="5.1 ELIGIBILITY", text="Fifteen days.")]
    gateway = LLMGateway(client_with(Recorder()))

    result = gateway.answer("How much leave?", sections)

    assert result.fallback is False
    assert result.answer == "Fifteen days."
    assert [c.section_id for c in result.citations] == [42]


def test_the_gateway_turns_a_dead_model_into_the_hr_fallback():
    """Never an error to the employee: the contracts are explicit that a
    provider error is one of the conditions producing the fallback."""
    sections = [PromptSection(section_id=42, heading="5.1 ELIGIBILITY", text="Fifteen days.")]
    sent = Recorder(replies=[urllib.error.URLError("connection refused")])

    result = LLMGateway(client_with(sent)).answer("How much leave?", sections)

    assert result.fallback is True
    assert "could not reach" in (result.reason or "")


def test_the_gateway_drops_a_citation_the_model_invented():
    """What disqualified llama3.2 during selection: it cites the
    handbook's own numbering rather than the section id it was given, and
    an answer with no verifiable citation is not an answer."""
    sections = [PromptSection(section_id=42, heading="5.1 ELIGIBILITY", text="Fifteen days.")]
    invented = '{"answer": "Fifteen days.", "citations": [{"section_id": 51}]}'

    result = LLMGateway(client_with(replying({"response": invented}))).answer("?", sections)

    assert result.fallback is True
    assert "no citation" in (result.reason or "")
