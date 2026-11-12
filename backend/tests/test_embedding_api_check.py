"""The ON-10 Embedding API check behaves, without calling anybody.

The script's whole job is to tell the truth about a provider we cannot
reach from a test: that it answered, that the vector is the width the
Vector Database will be built for, and that nothing printed along the way
contains the key. Those are the things tested here, with the transport
replaced so no request leaves the machine.
"""

import importlib.util
import json
import sys
import urllib.error

import pytest

from app.config import REPO_ROOT, Settings

SCRIPT_PATH = REPO_ROOT / "scripts" / "check_embedding_api.py"
KEY = "sk-test-not-a-real-key"


def _load_script():
    """Import the developer script by path; scripts/ is not a package.

    The module goes into sys.modules before it is executed because
    @dataclass looks its own module up there while the class body runs.
    """
    spec = importlib.util.spec_from_file_location("check_embedding_api", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check_embedding_api = _load_script()


@pytest.fixture
def settings(monkeypatch) -> Settings:
    monkeypatch.setenv("EMBEDDING_API_KEY", KEY)
    return Settings()


def _answer(dimensions: int) -> bytes:
    vector = [0.1] * dimensions
    return json.dumps({"data": [{"embedding": vector}]}).encode("utf-8")


def _http_error(code: int, body: str) -> urllib.error.HTTPError:
    error = urllib.error.HTTPError(
        url="https://api.openai.com/v1/embeddings", code=code, msg="", hdrs=None, fp=None
    )
    error.read = lambda: body.encode("utf-8")  # type: ignore[method-assign]
    return error


# --- the request we send -----------------------------------------------


def test_the_request_carries_the_key_and_the_chosen_model(settings):
    request = check_embedding_api.build_request(settings, "hello", KEY)

    assert request.method == "POST"
    assert request.full_url == settings.embedding_api_url
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    body = json.loads(request.data.decode("utf-8"))
    assert body == {"input": "hello", "model": "text-embedding-3-small"}


# --- what we make of the answer ----------------------------------------


def test_a_good_answer_reports_the_width_and_the_time(settings):
    outcome = check_embedding_api.check(
        settings, send=lambda request, timeout: _answer(settings.embedding_dimensions)
    )

    assert outcome.ok
    assert outcome.dimensions == 1536
    assert outcome.seconds is not None


def test_the_wrong_width_fails_and_names_both_numbers(settings):
    """A 3072-dimension model in a 1536-dimension collection breaks retrieval."""
    outcome = check_embedding_api.check(settings, send=lambda request, timeout: _answer(3072))

    assert not outcome.ok
    assert "3072" in outcome.message
    assert "1536" in outcome.message


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": []},
        {"data": ["not an object"]},
        {"data": [{}]},
        {"data": [{"embedding": []}]},
        {"data": [{"embedding": ["not a number"]}]},
    ],
)
def test_a_malformed_answer_is_rejected(payload):
    with pytest.raises(ValueError):
        check_embedding_api.read_embedding(payload)


def test_text_that_is_not_json_is_reported_not_raised(settings):
    outcome = check_embedding_api.check(settings, send=lambda request, timeout: b"<html>502")

    assert not outcome.ok
    assert "unexpected response" in outcome.message


# --- failures the developer running this will actually hit --------------


def test_no_key_fails_before_any_request_is_made(monkeypatch):
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)

    def refuse(request, timeout):  # pragma: no cover - must not be reached
        raise AssertionError("a request was sent without a key")

    outcome = check_embedding_api.check(Settings(_env_file=None), send=refuse)

    assert not outcome.ok
    assert "EMBEDDING_API_KEY" in outcome.message


def test_a_rejected_key_says_so(settings):
    def unauthorised(request, timeout):
        raise _http_error(401, '{"error": {"message": "Incorrect API key"}}')

    outcome = check_embedding_api.check(settings, send=unauthorised)

    assert not outcome.ok
    assert "401" in outcome.message
    assert "revoked" in outcome.message


def test_an_unreachable_provider_says_so(settings):
    def offline(request, timeout):
        raise urllib.error.URLError("getaddrinfo failed")

    outcome = check_embedding_api.check(settings, send=offline)

    assert not outcome.ok
    assert "could not reach the provider" in outcome.message


def test_a_timeout_names_the_limit(settings):
    def never_answers(request, timeout):
        raise TimeoutError

    outcome = check_embedding_api.check(settings, send=never_answers)

    assert not outcome.ok
    assert "10.0 seconds" in outcome.message


# --- the key never reaches the terminal --------------------------------


def test_an_error_that_echoes_the_key_is_redacted(settings):
    """Some providers quote the offending key back at you."""

    def chatty(request, timeout):
        raise _http_error(401, f'{{"error": "the key {KEY} is not valid"}}')

    outcome = check_embedding_api.check(settings, send=chatty)

    assert KEY not in outcome.message
    assert "***" in outcome.message


def test_the_script_never_prints_the_key_on_success(settings, capsys, monkeypatch):
    monkeypatch.setattr(check_embedding_api, "get_settings", lambda: settings, raising=True)
    monkeypatch.setattr(
        check_embedding_api,
        "check",
        lambda s, text: check_embedding_api.Outcome(
            ok=True, message="fine", dimensions=1536, seconds=0.2
        ),
    )

    assert check_embedding_api.main([]) == 0

    printed = capsys.readouterr()
    assert KEY not in printed.out + printed.err
    assert "text-embedding-3-small" in printed.out


def test_the_script_exits_non_zero_when_the_check_fails(settings, capsys, monkeypatch):
    monkeypatch.setattr(check_embedding_api, "get_settings", lambda: settings, raising=True)
    monkeypatch.setattr(
        check_embedding_api,
        "check",
        lambda s, text: check_embedding_api.Outcome(ok=False, message="no key"),
    )

    assert check_embedding_api.main([]) == 1
    assert "FAILED" in capsys.readouterr().err
