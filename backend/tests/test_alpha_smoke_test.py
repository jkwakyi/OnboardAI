"""The ON-26 smoke test script behaves, without a running stack.

A smoke test is only worth its output if the output means something, and
two things here decide that. The thresholds it measures against have to
be the ones the design fixes rather than numbers that drifted, and the
reset has to refuse to run anywhere it could destroy data somebody wanted.

The run itself cannot be tested from here - it needs a backend, both
databases and a local model, which is the entire point of it existing
separately from the suite. What is tested is the machinery around it.
"""

import importlib.util
import sys

import pytest

from app.config import REPO_ROOT, Settings
from app.services.llm.gateway import TIMEOUT_SECONDS

SCRIPT_PATH = REPO_ROOT / "scripts" / "alpha_smoke_test.py"


def _load_script():
    """Import the developer script by path; scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location("alpha_smoke_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = _load_script()


@pytest.fixture(autouse=True)
def never_read_the_developers_env_file(monkeypatch):
    """`main` loads `.env`; from here that would poison the whole run.

    Not hypothetical, and not a guess: the first version of this script
    called `load_dotenv` at module scope, so merely importing it put
    LLM_PROVIDER, AUTH_SECRET_KEY and the seed passwords into
    `os.environ` for every test in the process. Eleven tests in
    test_chat_api.py and test_config.py failed, and only on a machine
    with a configured `.env` - the same shape of failure the
    `ignore_the_developers_env_file` fixture in conftest exists for,
    which could not help because that fixture stops pydantic reading the
    *file* and this had already copied it into the environment.
    """
    monkeypatch.setattr(smoke, "load_environment", lambda: smoke.API)


# --- importing it must be harmless --------------------------------------


def test_importing_the_script_touches_nothing():
    """The regression test for the bug described in the fixture above.

    A developer script is imported by its test, and anything it does at
    module scope happens to the whole pytest process. This asserts the
    two that bit: nothing read from `.env` reaches the environment, and
    the module holds no live settings read at import time.
    """
    import os

    before = dict(os.environ)
    reloaded = _load_script()

    assert dict(os.environ) == before
    assert reloaded.API.startswith("http")


# --- the thresholds mean something --------------------------------------


def test_the_ask_limit_is_the_gateways_and_not_a_number_of_its_own():
    """If these drift apart the test starts passing questions the employee
    never saw an answer to: past 20 seconds the Gateway has already
    returned the HR fallback, so a 25-second 'pass' would be measuring a
    request that failed."""
    assert smoke.ASK_LIMIT_SECONDS == TIMEOUT_SECONDS


def test_the_target_is_inside_the_limit():
    """A target at or above the limit is not a target."""
    assert smoke.ASK_TARGET_SECONDS < smoke.ASK_LIMIT_SECONDS


def test_the_thresholds_are_the_ones_that_were_measured():
    """Asserted as values, not against each other. ON-18 measured 3.7 to
    8.2 seconds for an ask and 0.4 to 1.9 for an upload; these leave room
    for a slower answer without quietly accepting a regression. Moving
    them needs a measurement, so moving them should fail here first.
    """
    assert smoke.ASK_TARGET_SECONDS == 12.0
    assert smoke.UPLOAD_LIMIT_SECONDS == 10.0


# --- the clean setup is the dangerous part ------------------------------


def test_it_refuses_to_run_outside_development(monkeypatch, capsys):
    """The run empties documents, sections, vectors, chat logs and
    escalations. Everywhere that is not a developer's machine, that is
    data somebody wanted."""
    monkeypatch.setattr(sys, "argv", ["alpha_smoke_test.py"])
    monkeypatch.setattr(
        smoke,
        "get_settings",
        lambda: Settings(_env_file=None, onboardai_env="production"),
        raising=False,
    )
    # The script reads get_settings from app.config at call time.
    import app.config

    monkeypatch.setattr(
        app.config,
        "get_settings",
        lambda: Settings(_env_file=None, onboardai_env="production"),
    )

    assert smoke.main() == 2
    assert "will not run outside development" in capsys.readouterr().err


def test_it_refuses_to_run_against_the_mock_model(monkeypatch, capsys):
    """The ticket asks for a cited answer from the real LLM. Against the
    mock every answer says it came from a mock, and the run would report
    a pass for the one thing it was built to prove."""
    monkeypatch.setattr(sys, "argv", ["alpha_smoke_test.py"])
    import app.config

    monkeypatch.setattr(
        app.config,
        "get_settings",
        lambda: Settings(_env_file=None, onboardai_env="development", llm_provider="mock"),
    )

    assert smoke.main() == 2
    assert "not 'real'" in capsys.readouterr().err


# --- reporting ----------------------------------------------------------


def test_a_check_records_its_own_verdict():
    report = smoke.Report()

    assert report.check("something true", True) is True
    assert report.check("something false", False, "why") is False
    assert [name for name, _, _ in report.failures] == ["something false"]


def test_the_summary_exits_non_zero_when_anything_failed(monkeypatch, capsys):
    """A smoke test that printed FAIL and exited 0 would be worse than
    none: CI and a human skimming would both read it as a pass."""
    monkeypatch.setattr(smoke, "report", smoke.Report())
    smoke.report.check("fine", True)
    assert smoke.summary() == 0

    monkeypatch.setattr(smoke, "report", smoke.Report())
    smoke.report.check("broken", False, "detail")
    assert smoke.summary() == 1
    assert "FAILED: broken" in capsys.readouterr().out


def test_the_token_reader_survives_rubbish():
    """It reads the role out of a token to check the server put it there.
    Handed something that is not a token it must return nothing rather
    than raise, so a failed login reports as a failed check."""
    assert smoke._claims_in("") == {}
    assert smoke._claims_in("not.a.token") == {}
    assert smoke._claims_in("onepart") == {}


def test_the_token_reader_finds_the_role():
    import base64
    import json

    payload = base64.urlsafe_b64encode(json.dumps({"role": "employee"}).encode()).decode()
    assert smoke._claims_in(f"header.{payload.rstrip('=')}.signature")["role"] == "employee"


# --- what it says is missing ---------------------------------------------


def test_the_absent_endpoints_are_the_ones_that_are_absent():
    """This list is the honest half of the report. If somebody builds
    ON-16 and leaves it here, the run starts asserting that a working
    endpoint is missing and fails - which is the right way round.
    """
    from app.api.router import api_router

    routed = {(method, route.path) for route in api_router.routes for method in route.methods}

    for method, path in (
        ("GET", "/api/documents"),
        ("DELETE", "/api/documents/{document_id}"),
        ("POST", "/api/chat/feedback"),
        ("GET", "/api/escalations"),
        ("PATCH", "/api/escalations/{escalation_id}"),
    ):
        assert (method, path) not in routed, (
            f"{method} {path} now exists - update section 8 of the smoke test"
        )


@pytest.mark.parametrize(
    "path",
    ["/api/auth/login", "/api/documents", "/api/chat/ask", "/api/escalations"],
)
def test_the_endpoints_the_alpha_does_have_are_routed(path):
    from app.api.router import api_router

    assert any(route.path == path for route in api_router.routes), path
