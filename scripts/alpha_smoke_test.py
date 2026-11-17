"""The alpha end-to-end smoke test (ON-26).

Runs the whole alpha path against a running stack, on a clean setup, and
reports every check as a line you can read rather than a dot. The point
is not to replace the unit tests - there are 1,272 of those - but to
prove the modules work *together*, through HTTP, with the real embedding
provider and the real local model, which no unit test does.

    python scripts/alpha_smoke_test.py

It needs the backend on :8000, PostgreSQL, ChromaDB and (for the real
provider) Ollama. It **wipes the documents, sections, vectors, chat logs
and escalations** first, because "on a clean setup" is what the ticket
asks and a knowledge base left over from the last run is how a smoke test
passes against data it did not create. It refuses to run outside
development for that reason. `--no-reset` skips the wipe when you only
want to re-measure.

What it does not cover, and deliberately:

* The pages. A browser walkthrough is a separate pass and a human one -
  this checks the API the pages call.
* `GET`/`DELETE /api/documents`, `POST /api/chat/feedback`,
  `GET`/`PATCH /api/escalations`. They do not exist yet (ON-16, ON-19,
  ON-21), and a smoke test that skipped them silently would read as a
  pass for a system that is five endpoints short.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

HANDBOOK = REPO_ROOT / "data" / "handbook" / "pdf"

# Set by `main`, because this script needs the developer's `.env` and
# importing it must not reach into the process environment to get one.
# `test_alpha_smoke_test.py` imports this module; loading `.env` at import
# time put LLM_PROVIDER, AUTH_SECRET_KEY and the seed passwords into
# `os.environ` for the whole pytest process, which no `monkeypatch.delenv`
# could then undo - eleven tests elsewhere in the suite failed, and only
# on a machine with a configured `.env`. Nothing at module scope here may
# read or write the environment.
API = "http://127.0.0.1:8000/api"

# --- the thresholds -----------------------------------------------------
#
# The ticket says "against the thresholds the team sets", and the team had
# not set any, so these are proposed here with their reasoning rather than
# left implicit. Only the first is fixed by anything outside this file.

# Fixed by the Interface Contracts: the LLM Gateway gives up at 20
# seconds. An ask that takes longer has already returned the HR fallback,
# so this is not a target - it is the line past which the system is
# answering a different question.
ASK_LIMIT_SECONDS = 20.0
# Measured, not contractual. qwen3:8b answered eight questions in 3.7 to
# 8.2 seconds with the model loaded (ON-18), so 12 leaves room for a
# longer answer without quietly accepting a regression to 19.
ASK_TARGET_SECONDS = 12.0
# Upload is synchronous through extract, section and embed (ON-39), and
# the handbook chapters took 0.4 to 1.9 seconds each. 10 is a wide margin
# that still catches an embedding provider having a bad day.
UPLOAD_LIMIT_SECONDS = 10.0

ANSWERABLE = "How much paid time off do I get?"
UNANSWERABLE = "What is the capital of Mongolia?"
HR_FALLBACK_OPENING = "I could not find an answer to that"


# --- reporting ----------------------------------------------------------


@dataclass
class Report:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    timings: dict[str, list[float]] = field(default_factory=dict)

    def check(self, name: str, passed: bool, detail: str = "") -> bool:
        self.checks.append((name, passed, detail))
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {name}" + (f" - {detail}" if detail else ""), flush=True)
        return passed

    def time(self, label: str, seconds: float) -> None:
        self.timings.setdefault(label, []).append(seconds)

    @property
    def failures(self) -> list[tuple[str, bool, str]]:
        return [c for c in self.checks if not c[1]]


report = Report()


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}", flush=True)


def load_environment() -> str:
    """Read the developer's `.env` and return the API base URL.

    A function, called from `main`, rather than module-level code - see
    the note beside `API`. A test monkeypatches this to keep the import
    harmless, which only works because it is something you can replace.
    """
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    return os.environ.get("SMOKE_API", API)


# --- HTTP ---------------------------------------------------------------


def call(method: str, path: str, *, token=None, body=None, files=None, timeout=120.0):
    """Returns (status, parsed body, seconds). Never raises for an HTTP code."""
    headers = {}
    data = None

    if files is not None:
        filename, blob, content_type = files
        boundary = f"----onboardai{int(time.time() * 1000)}"
        data = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                blob,
                f"\r\n--{boundary}--\r\n".encode(),
            ]
        )
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as refused:
        raw, status = refused.read(), refused.code
    except urllib.error.URLError as unreachable:
        return 0, {"detail": str(unreachable.reason)}, time.monotonic() - started

    took = time.monotonic() - started
    try:
        return status, json.loads(raw or b"{}"), took
    except json.JSONDecodeError:
        return status, {"raw": raw[:200].decode("utf-8", "replace")}, took


# --- the clean setup ----------------------------------------------------


def reset() -> None:
    """Empty the knowledge base, the chat logs and the escalations."""
    import psycopg

    from app.config import get_settings
    from app.vectorstore.chroma import get_client

    settings = get_settings()
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as connection:
        for table in ("escalations", "chat_logs", "sections", "documents"):
            connection.execute(f"delete from {table}")
        connection.commit()

    storage = REPO_ROOT / settings.file_storage_dir
    if storage.is_dir():
        for stored in storage.iterdir():
            if stored.is_file():
                stored.unlink()

    client = get_client()
    try:
        client.delete_collection(settings.chroma_collection)
    except Exception:  # noqa: BLE001 - absent is the state we want
        pass

    print("  knowledge base, chat logs and escalations cleared", flush=True)


# --- 1. authentication --------------------------------------------------


def _claims_in(token: str) -> dict:
    """The token's payload, read without verifying it.

    Read, not trusted: this is a test asserting what the server put in,
    and the server is the thing that verifies on the way back in.
    """
    import base64

    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except (IndexError, ValueError, json.JSONDecodeError):
        return {}


def authentication() -> tuple[str, str]:
    section("1. Authentication (step 1, ON-13)")

    status, body, _ = call(
        "POST", "/auth/login", body={"email": "hr@onboardai.example", "password": "wrong"}
    )
    report.check(
        "an invalid password is refused with 401",
        status == 401,
        f"got {status}",
    )
    report.check(
        "the refusal does not say whether the account exists",
        "password" not in json.dumps(body).lower() or "incorrect" in json.dumps(body).lower(),
        str(body.get("detail", ""))[:60],
    )

    status, body, _ = call(
        "POST",
        "/auth/login",
        body={"email": "nobody@onboardai.example", "password": "whatever"},
    )
    report.check("an unknown account is refused with 401", status == 401, f"got {status}")

    hr_token = employee_token = ""
    for label, email, variable, role in (
        ("HR administrator", "hr@onboardai.example", "SEED_HR_PASSWORD", "hr_administrator"),
        ("employee", "employee@onboardai.example", "SEED_EMPLOYEE_PASSWORD", "employee"),
    ):
        password = os.environ.get(variable)
        if not password:
            report.check(f"{label} can log in", False, f"{variable} is not set")
            continue
        status, body, took = call(
            "POST", "/auth/login", body={"email": email, "password": password}
        )
        report.time("login", took)
        # The contracts return the token and nothing else; the role rides
        # inside it, which is what the page reads to build its navigation.
        claims = _claims_in(body.get("token") or "")
        ok = report.check(
            f"the {label} can log in and the token carries their role",
            status == 200 and bool(body.get("token")) and claims.get("role") == role,
            f"{status}, role={claims.get('role')}",
        )
        if ok and role == "hr_administrator":
            hr_token = body["token"]
        elif ok:
            employee_token = body["token"]

    return hr_token, employee_token


# --- 2. Auth Check ------------------------------------------------------


def auth_check(hr_token: str, employee_token: str) -> None:
    section("2. Auth Check rejects what it should (step 2, ON-14)")

    # A *routed* path, deliberately. Auth Check hangs off the router, so an
    # unmatched path answers 404 before it ever runs - checking one of those
    # would pass without the guard existing at all.
    status, _, _ = call("POST", "/chat/ask", token=None, body={"question": "hi"})
    report.check("no token at all is refused with 401", status == 401, f"got {status}")

    status, _, _ = call("POST", "/chat/ask", token="not-a-token", body={"question": "hi"})
    report.check("a malformed token is refused with 401", status == 401, f"got {status}")

    status, _, _ = call("POST", "/chat/ask", token=hr_token + "x", body={"question": "hi"})
    report.check("a tampered token is refused with 401", status == 401, f"got {status}")

    status, _, _ = call(
        "POST",
        "/documents",
        token=employee_token,
        files=("notes.txt", b"Employees get 15 days.", "text/plain"),
    )
    report.check(
        "an employee cannot upload a document (HR only)",
        status == 403,
        f"got {status}",
    )


# --- 3. upload ----------------------------------------------------------


def upload(hr_token: str) -> None:
    section("3. The HR administrator uploads the handbook (U1-U4, ON-15)")

    pdfs = sorted(HANDBOOK.glob("*.pdf"))
    if not report.check(f"the handbook is present ({len(pdfs)} chapters)", bool(pdfs)):
        return

    slowest = 0.0
    uploaded = 0
    for pdf in pdfs:
        status, body, took = call(
            "POST",
            "/documents",
            token=hr_token,
            files=(pdf.name, pdf.read_bytes(), "application/pdf"),
        )
        report.time("upload", took)
        slowest = max(slowest, took)
        if status == 201 and body.get("id"):
            uploaded += 1
        else:
            report.check(f"{pdf.name} uploaded", False, f"{status} {body}")

    report.check(
        f"all {len(pdfs)} chapters uploaded and were read on the way in",
        uploaded == len(pdfs),
        f"{uploaded} of {len(pdfs)}, slowest {slowest:.1f}s",
    )
    report.check(
        f"every upload finished inside {UPLOAD_LIMIT_SECONDS:.0f}s",
        slowest <= UPLOAD_LIMIT_SECONDS,
        f"slowest {slowest:.1f}s",
    )

    status, _, _ = call(
        "POST",
        "/documents",
        token=hr_token,
        files=("payroll.xlsx", b"PK\x03\x04not-a-document", "application/vnd.ms-excel"),
    )
    report.check(
        "an unsupported file type is refused rather than stored",
        status == 415,
        f"got {status}",
    )

    status, _, _ = call(
        "POST",
        "/documents",
        token=hr_token,
        files=("empty.txt", b"   \n  ", "text/plain"),
    )
    # 422 rather than 400: the request was well formed and the file is what
    # it claims to be, there is simply nothing in it to answer from.
    report.check(
        "a document with no readable text is refused",
        status == 422,
        f"got {status}",
    )

    _knowledge_base_landed(len(pdfs))


def _knowledge_base_landed(expected_documents: int) -> None:
    """Both databases agree, which is the thing U4 can get wrong."""
    import psycopg

    from app.config import get_settings
    from app.vectorstore.chroma import get_collection

    settings = get_settings()
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as connection:
        documents = connection.execute("select count(*) from documents").fetchone()[0]
        sections = connection.execute("select count(*) from sections").fetchone()[0]

    vectors = get_collection().count()

    report.check(
        f"{expected_documents} documents and their sections are in PostgreSQL",
        documents == expected_documents and sections > 0,
        f"{documents} documents, {sections} sections",
    )
    report.check(
        "every section has a vector in ChromaDB",
        vectors == sections,
        f"{vectors} vectors for {sections} sections",
    )


# --- 4. asking ----------------------------------------------------------


def asking(employee_token: str) -> int | None:
    section("4. An employee asks (steps 1-9, ON-17, ON-18)")

    # The first question after the model has been unloaded pays its load,
    # which is about a minute and past the Gateway's limit (TD-36). That is
    # a real property of the system and it is reported below rather than
    # hidden - but measuring the *answer* path against it would be
    # measuring Ollama's disk read, so the timed question comes second.
    _, _, cold = call("POST", "/chat/ask", token=employee_token, body={"question": ANSWERABLE})
    report.time("ask (first, possibly cold)", cold)
    print(
        f"         first question took {cold:.1f}s"
        + ("  <- the model was loaded on demand, TD-36" if cold > ASK_TARGET_SECONDS else ""),
        flush=True,
    )

    status, body, took = call(
        "POST", "/chat/ask", token=employee_token, body={"question": ANSWERABLE}
    )
    report.time("ask (answered)", took)

    answered = report.check(
        "an answerable question is answered rather than refused",
        status == 200 and body.get("fallback") is False,
        f"{status}, fallback={body.get('fallback')}",
    )
    if answered:
        citations = body.get("citations") or []
        report.check(
            "the answer carries at least one citation",
            bool(citations),
            f"{len(citations)} citation(s)",
        )
        report.check(
            "the citation names the chapter that answers the question",
            any("time-off" in (c.get("document") or "") for c in citations),
            ", ".join(f"{c.get('document')} / {c.get('heading')}" for c in citations)[:90],
        )
        report.check(
            "the answer is not the Mock LLM's",
            "Mock LLM" not in (body.get("answer") or ""),
            (body.get("answer") or "")[:70],
        )
        print(f"         answer: {(body.get('answer') or '')[:150]}", flush=True)

    report.check(
        f"the answer came back inside the Gateway's {ASK_LIMIT_SECONDS:.0f}s",
        took <= ASK_LIMIT_SECONDS,
        f"{took:.1f}s",
    )
    report.check(
        f"...and, with the model loaded, inside the {ASK_TARGET_SECONDS:.0f}s target",
        took <= ASK_TARGET_SECONDS,
        f"{took:.1f}s",
    )
    report.check(
        "even a cold first question stays inside the contractual limit",
        cold <= ASK_LIMIT_SECONDS,
        f"{cold:.1f}s - if this fails it is TD-36, not a regression",
    )

    status, body, took = call(
        "POST", "/chat/ask", token=employee_token, body={"question": UNANSWERABLE}
    )
    report.time("ask (fallback)", took)
    fell_back = report.check(
        "an unanswerable question returns the HR fallback, not an error",
        status == 200 and body.get("fallback") is True,
        f"{status}, fallback={body.get('fallback')}",
    )
    report.check(
        "the fallback points the employee at HR",
        (body.get("answer") or "").startswith(HR_FALLBACK_OPENING),
        (body.get("answer") or "")[:70],
    )
    report.check(
        "the fallback cites nothing, because nothing was used",
        not (body.get("citations") or []),
        f"{len(body.get('citations') or [])} citation(s)",
    )
    report.check(
        "the model was never asked, so the refusal is fast",
        took < ASK_TARGET_SECONDS,
        f"{took:.1f}s",
    )

    status, _, _ = call("POST", "/chat/ask", token=employee_token, body={"question": "   "})
    report.check("an empty question is refused with 422", status == 422, f"got {status}")

    status, _, _ = call("POST", "/chat/ask", token=employee_token, body={"question": "x" * 2001})
    report.check("an oversized question is refused with 422", status == 422, f"got {status}")

    return body.get("id") if fell_back else None


# --- 5. the model failing -----------------------------------------------


def model_failures() -> None:
    """In-process, because the running backend has one configuration.

    These are three of the four conditions the contracts say produce the
    HR fallback. The fourth - below the relevance threshold - is checked
    through HTTP above.
    """
    section("5. The model failing produces the HR fallback (ON-45, ON-18)")

    from app.config import Settings, get_settings
    from app.services.llm.gateway import LLMGateway, PromptSection
    from app.services.llm.real import RealLLMClient

    sections = [
        PromptSection(section_id=1, heading="4.1 PAID TIME OFF", text="Fifteen days a year.")
    ]
    settings = get_settings()

    missing = Settings(
        _env_file=None,
        llm_provider="real",
        llm_model="a-model-nobody-pulled:70b",
        llm_api_url=settings.llm_api_url,
    )
    result = LLMGateway(RealLLMClient(missing)).answer(ANSWERABLE, sections)
    report.check(
        "a model that is not there falls back rather than erroring",
        result.fallback is True,
        (result.reason or "")[:70],
    )

    unreachable = Settings(
        _env_file=None,
        llm_provider="real",
        llm_model=settings.llm_model,
        llm_api_url="http://127.0.0.1:1/api/generate",
    )
    result = LLMGateway(RealLLMClient(unreachable)).answer(ANSWERABLE, sections)
    report.check(
        "a model server that is down falls back rather than erroring",
        result.fallback is True,
        (result.reason or "")[:70],
    )

    started = time.monotonic()
    result = LLMGateway(RealLLMClient(), timeout_seconds=0.05).answer(ANSWERABLE, sections)
    waited = time.monotonic() - started
    report.check(
        "a model that does not answer in time falls back",
        result.fallback is True,
        (result.reason or "")[:60],
    )
    report.check(
        "...and the employee stops waiting when the limit says so",
        waited < 2.0,
        f"waited {waited:.2f}s",
    )


# --- 6. escalation ------------------------------------------------------


def escalation(employee_token: str, chat_log_id: int | None) -> None:
    section("6. The employee sends the question to HR (E1-E2, ON-20)")

    if chat_log_id is None:
        report.check("there is a fallback to escalate", False, "no chat log id from step 4")
        return

    status, body, took = call(
        "POST", "/escalations", token=employee_token, body={"chat_log_id": chat_log_id}
    )
    report.time("escalate", took)
    report.check("the fallback can be sent to HR", status == 201, f"got {status}")
    report.check(
        "HR receives the question as the employee asked it",
        body.get("question") == UNANSWERABLE,
        str(body.get("question"))[:60],
    )
    report.check("it arrives open, waiting for a reply", body.get("status") == "open")

    status, again, _ = call(
        "POST", "/escalations", token=employee_token, body={"chat_log_id": chat_log_id}
    )
    report.check(
        "sending it twice does not put it in the inbox twice",
        again.get("id") == body.get("id"),
        f"ids {body.get('id')} and {again.get('id')}",
    )

    status, _, _ = call("POST", "/escalations", token=employee_token, body={"chat_log_id": 99999})
    report.check("an answer that is not yours cannot be escalated", status == 404, f"got {status}")


# --- 7. secrets ---------------------------------------------------------


def secrets_stay_out_of_the_repository() -> None:
    section("7. Keys are not in the repository")

    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()

    report.check(
        "no .env file is tracked by git",
        not [name for name in tracked if Path(name).name == ".env"],
    )
    report.check(
        ".env.example is tracked, so the shape is documented",
        ".env.example" in tracked,
    )

    for variable in ("EMBEDDING_API_KEY", "AUTH_SECRET_KEY"):
        secret = os.environ.get(variable) or ""
        if not secret:
            report.check(f"{variable} is set, so there is something to check", False)
            continue
        hits = subprocess.run(
            ["git", "grep", "-l", "--fixed-strings", secret],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        report.check(
            f"the live {variable} appears in no tracked file",
            not hits,
            hits[:80],
        )

    # The frontend is served to the browser, so anything secret reaching it
    # is public. The API client reads one variable and it is a URL.
    vite_variables = subprocess.run(
        ["git", "grep", "-oh", "-E", r"VITE_[A-Z0-9_]+", "--", "frontend/src"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    report.check(
        "the frontend reads no VITE_ variable that could hold a secret",
        set(vite_variables) <= {"VITE_API_BASE_URL"},
        ", ".join(sorted(set(vite_variables))) or "none",
    )


# --- 8. what is not built yet -------------------------------------------


def not_built_yet(hr_token: str, employee_token: str) -> None:
    section("8. The endpoints the alpha does not have")

    for method, path, token, ticket in (
        ("GET", "/documents", hr_token, "ON-16"),
        ("DELETE", "/documents/1", hr_token, "ON-16"),
        ("POST", "/chat/feedback", employee_token, "ON-19"),
        ("GET", "/escalations", hr_token, "ON-21"),
        ("PATCH", "/escalations/1", hr_token, "ON-21"),
    ):
        status, _, _ = call(method, path, token=token, body={} if method != "GET" else None)
        report.check(
            f"{method} /api{path} is absent, as expected ({ticket})",
            status in (404, 405),
            f"got {status}",
        )


# --- the run ------------------------------------------------------------


def summary() -> int:
    section("Timings")
    for label, values in report.timings.items():
        print(
            f"  {label:18} n={len(values):<3} "
            f"median {sorted(values)[len(values) // 2]:5.2f}s  slowest {max(values):5.2f}s",
            flush=True,
        )

    passed = len(report.checks) - len(report.failures)
    section("Result")
    print(f"  {passed} of {len(report.checks)} checks passed", flush=True)
    for name, _, detail in report.failures:
        print(f"  FAILED: {name} - {detail}", flush=True)
    return 1 if report.failures else 0


def main() -> int:
    global API

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--no-reset", action="store_true", help="keep whatever is already in the databases"
    )
    arguments = parser.parse_args()

    API = load_environment()

    from app.config import get_settings

    settings = get_settings()
    if settings.onboardai_env != "development":
        print(
            f"ONBOARDAI_ENV is {settings.onboardai_env!r}. This test empties the "
            f"knowledge base and will not run outside development.",
            file=sys.stderr,
        )
        return 2

    print(f"OnboardAI alpha smoke test\nAPI: {API}", flush=True)
    print(f"LLM_PROVIDER={settings.llm_provider}  model={settings.llm_model}", flush=True)
    print(
        f"EMBEDDING_PROVIDER={settings.embedding_provider}  model={settings.embedding_model}",
        flush=True,
    )

    if settings.llm_provider != "real":
        print(
            "\nLLM_PROVIDER is not 'real'. The ticket asks for an answer from the "
            "real LLM, so this run cannot satisfy it.",
            file=sys.stderr,
        )
        return 2

    section("0. A clean setup")
    if arguments.no_reset:
        print("  skipped (--no-reset)", flush=True)
    else:
        reset()

    hr_token, employee_token = authentication()
    if not hr_token or not employee_token:
        print("\nCannot continue without both logins.", file=sys.stderr)
        return summary() or 1

    auth_check(hr_token, employee_token)
    upload(hr_token)
    chat_log_id = asking(employee_token)
    model_failures()
    escalation(employee_token, chat_log_id)
    secrets_stay_out_of_the_repository()
    not_built_yet(hr_token, employee_token)

    return summary()


if __name__ == "__main__":
    raise SystemExit(main())
