# Technical debt log

Every shortcut and temporary solution taken while building OnboardAI, with
what it costs us and how we plan to pay it back.

This is kept honestly. An entry here is not an admission of carelessness —
most of these were the right call under the alpha deadline. What would be
careless is taking a shortcut and not writing it down, because then nobody
knows the bill exists.

It is the source for the Refinement Report and the Unit 8 position paper.

**Add an entry in the same pull request as the shortcut**, not afterwards.
See [How to add an entry](#how-to-add-an-entry).

## Index

| ID | Debt | Area | Status |
| --- | --- | --- | --- |
| [TD-01](#td-01--the-mock-llm-is-the-default-provider) | The Mock LLM is the default provider | AI Chatbot Module | Open |
| [TD-02](#td-02--no-ci-pipeline) | No CI pipeline | Build | Open |
| [TD-03](#td-03--no-health-or-readiness-endpoint) | No health or readiness endpoint | Backend API | Accepted |
| [TD-04](#td-04--the-integration-tests-are-opt-in) | The integration tests are opt-in | Testing | Open |
| [TD-05](#td-05--generated-pdfs-are-committed) | Generated PDFs are committed | Data | Accepted |
| [TD-06](#td-06--the-chroma-client-and-server-versions-are-coupled-by-hand) | The Chroma client and server versions are coupled by hand | Storage | Open |
| [TD-07](#td-07--python-314-is-not-supported) | Python 3.14 is not supported | Build | Open |
| [TD-08](#td-08--lint-configuration-sits-under-backend-but-covers-the-repository) | Lint configuration sits under `backend/` but covers the repository | Build | Open |
| [TD-09](#td-09--the-frontend-is-a-placeholder) | The frontend is a placeholder | Frontend | Open |
| [TD-10](#td-10--no-migration-tooling-for-the-main-database) | No migration tooling for the Main Database | Storage | Open |
| [TD-11](#td-11--the-watcher-parses-test-output-with-regular-expressions) | The watcher parses test output with regular expressions | Tooling | Accepted |
| [TD-12](#td-12--the-jira-board-snapshot-is-only-as-fresh-as-the-last-sync) | The Jira board snapshot is only as fresh as the last sync | Tooling | Accepted |
| [TD-13](#td-13--nothing-automated-proves-the-embedding-api-still-answers) | Nothing automated proves the Embedding API still answers | AI Chatbot Module | Open |

Status is **Open** (we intend to pay it back), **Accepted** (we have decided
to live with it, and the entry says why), or **Mitigated** (paid back; kept
for the record, with what fixed it).

---

### TD-01 — The Mock LLM is the default provider

**Taken:** 11 November 2026, in ON-9 · **Status:** Open · **Ticket:** ON-18

**What.** `LLM_PROVIDER` defaults to `mock`. No real language model is wired
in, and the `LLMProvider` interface has no production implementation yet.

**Why.** Backend and frontend work could not wait for a model to be chosen,
and the design requires that the Mock LLM stays selectable so CI and
teammates without the model can still run the system.

**Impact.** Nothing exercises the real `generate(prompt)` path. The 20-second
timeout, the JSON validation in the LLM Gateway, and the fallback behaviour
on a provider error are all untested against anything that can actually fail
in those ways. Answer quality is entirely unmeasured.

**Mitigation.** ON-18 selects a real provider and wires it behind the same
interface; the Mock LLM remains selectable by configuration. ON-24 then
measures answer quality against the evaluation set. Until then, no claim
about answer quality is supportable.

---

### TD-02 — No CI pipeline

**Taken:** 11 November 2026, in ON-9 · **Status:** Open · **Ticket:** ON-49

**What.** Tests and lint run only on developer machines. Nothing runs
automatically on a pull request.

**Why.** ON-49 builds the pipeline and was blocked by the scaffold in ON-9.

**Impact.** A pull request can merge with failing tests; nobody would know.
The board rule that a ticket is Done when "CI is green" currently degrades to
"the author ran the tests". Development happens on Windows while CI will run
Linux, so a Windows-only assumption could reach `main` unnoticed — the kind
of thing that surfaces at the worst moment.

**Mitigation.** ON-49. Until it exists, every ticket records in its Jira
comment exactly which commands were run and what passed, so the evidence is
at least written down.

---

### TD-03 — No health or readiness endpoint

**Taken:** 11 November 2026, in ON-9 · **Status:** Accepted

**What.** Whether the backend can reach PostgreSQL and ChromaDB is reported
in the startup log and asserted by integration tests. It is not exposed over
HTTP.

**Why.** The Interface Contracts define exactly nine endpoints and no health
route. Inventing one would have broken the rule that the contracts are the
source of truth, for a convenience rather than a requirement.

**Impact.** There is no HTTP readiness probe. Checking that a running backend
is healthy means reading its log or running the integration tests. If we ever
containerise the backend or put it behind a load balancer, we will want one.

**Mitigation.** Accepted for the alpha. If ON-49 or deployment needs a probe,
raise it as a contracts change with the team rather than adding an endpoint
quietly.

---

### TD-04 — The integration tests are opt-in

**Taken:** 11 November 2026, in ON-9 · **Status:** Open · **Ticket:** ON-49

**What.** `backend/pyproject.toml` sets `addopts = "-m 'not integration'"`, so
the tests that talk to PostgreSQL and ChromaDB are deselected by default. They
run only with `pytest -m integration`.

**Why.** It keeps the default suite fast and lets a teammate run the tests
without Docker running.

**Impact.** The only tests that prove the backend can reach its stores do not
run unless someone remembers the flag. They can break and stay broken without
anyone noticing, which is the worst property a test can have.

**Mitigation.** ON-49 should run them as a separate job with service
containers, so they are exercised on every pull request even though they stay
out of the fast local suite.

---

### TD-05 — Generated PDFs are committed

**Taken:** 11 November 2026, in ON-12 · **Status:** Accepted

**What.** `data/handbook/pdf/*.pdf` are build output from
`scripts/build_handbook_pdfs.py`, committed to the repository.

**Why.** The contracts accept PDF and TXT, and the alpha smoke test needs real
PDFs to upload. Generating them at test time would put `reportlab` on the
critical path of every checkout.

**Impact.** Binary files in the history, and an edit to a TXT without
rerunning the script leaves the PDFs stale.

**Mitigation.** `test_pdf_is_readable_and_matches_its_source` fails if the two
drift, so staleness is caught rather than shipped. If CI gains a build step,
generate them there and stop committing them.

---

### TD-06 — The Chroma client and server versions are coupled by hand

**Taken:** 11 November 2026, in ON-9 · **Status:** Open

**What.** `backend/pyproject.toml` pins `chromadb>=1.5,<2` and
`docker-compose.yml` pins `chromadb/chroma:1.5.9`. The two must be upgraded
together.

**Why.** A 1.x client speaks `/api/v2` and cannot talk to an 0.6.x server. We
found this by pinning them independently and watching the connection fail.

**Impact.** Upgrading one without the other breaks every retrieval path, with
an error that does not obviously point at a version mismatch.

**Mitigation.** A comment in `docker-compose.yml` records the constraint. A CI
integration job (TD-04, ON-49) would catch a mismatch automatically, which is
the real fix.

---

### TD-07 — Python 3.14 is not supported

**Taken:** 11 November 2026, in ON-9 · **Status:** Open

**What.** `requires-python = ">=3.12,<3.14"`.

**Why.** Not every dependency publishes 3.14 wheels yet, and 3.14 is the
default interpreter on at least one developer machine — so the cap is load
bearing, not theoretical.

**Impact.** Contributors must install an older Python. A teammate who misses
this gets a confusing build failure during `pip install` rather than a clear
message.

**Mitigation.** The README states the supported versions. Lift the cap once
the dependencies publish 3.14 wheels, and remove this entry when we do.

---

### TD-08 — Lint configuration sits under `backend/` but covers the repository

**Taken:** 11 November 2026, in ON-12 · **Status:** Open

**What.** The `ruff` configuration lives in `backend/pyproject.toml`, but
there is Python in `scripts/` and `tools/` too. Linting those requires
`ruff check --config backend/pyproject.toml scripts tools`.

**Why.** The backend was the only Python in the repository when the config was
written. Moving it was out of scope for the tickets that added the other
directories.

**Impact.** It is easy to run `ruff check .` from `backend/` and believe the
repository is clean when two directories were never looked at. CI will have to
know the flag as well, which is a thing to get wrong once.

Worse, the two invocations disagree. Running from `backend/`, ruff treats
`app` as first-party and the import blocks in `backend/tests/` are correctly
sorted; running from the root with `--config backend/pyproject.toml`, it does
not, and reports those same files as unsorted. So there is currently **no
single command that lints the whole repository cleanly** — which is an
unpleasant thing to discover while writing a CI job.

**Mitigation.** Move the `ruff` configuration to a root `pyproject.toml` or
`ruff.toml` so a bare `ruff check .` covers everything. Small; no ticket yet.

---

### TD-09 — The frontend is a placeholder

**Taken:** 11 November 2026, in ON-9 · **Status:** Open · **Ticket:** ON-62

**What.** The React application renders a few static lines of text. There is
no routing, no API client, no design tokens and no styling beyond a base
font.

**Why.** ON-9 was scaffolding only. The interface is epic ON-62, which builds
tokens (ON-63), then shared components (ON-64), then the app shell (ON-65),
then the pages — deliberately in that order.

**Impact.** Nothing exercises the frontend beyond a build and two smoke tests.
The API client (ON-38) does not exist, so no page can talk to the backend yet,
and the whole frontend-to-backend path is unproven.

**Mitigation.** ON-63 → ON-64 → ON-65, then the pages. The placeholder text
names the tickets that replace it, and the quality rule is that placeholder
content goes as soon as the real thing exists.

---

### TD-10 — No migration tooling for the Main Database

**Taken:** 11 November 2026, in ON-9 · **Status:** Open

**What.** `backend/app/db/session.py` creates a SQLAlchemy engine, a session
factory and a declarative `Base`. There are no models, and no decision has
been made about how schema changes will be applied.

**Why.** The schema is ON-11, which was blocked by the scaffold. Choosing
migration tooling before there was a single table would have been guessing.

**Impact.** This is the entry most likely to bite after the alpha. The first
schema change against a database holding data has no upgrade path, and
"recreate the database" stops being acceptable the moment anyone has
uploaded documents they care about.

**Mitigation.** ON-11 creates the schema. Decide on migrations (Alembic is the
obvious choice with SQLAlchemy) at the same time rather than after — this
should be proposed as a ticket before ON-11 starts, not discovered later.

---

### TD-11 — The watcher parses test output with regular expressions

**Taken:** 11 November 2026, in the development watcher · **Status:** Accepted

**What.** `tools/watch/run.py` extracts progress and pass/fail counts by
matching patterns against pytest and vitest console output.

**Why.** It works with any command and needs no plugin wired into either test
runner. A structured reporter would have meant per-tool integration for a
development convenience.

**Impact.** A change to pytest's or vitest's output format silently stops
progress updating. A command the patterns do not recognise shows no
percentage.

**Mitigation.** Accepted. It degrades honestly: an unrecognised command still
shows its state, elapsed time, exit code and full output, so the watcher is
never wrong, only less detailed. Switch to pytest's JSON report if this
becomes a nuisance.

---

### TD-12 — The Jira board snapshot is only as fresh as the last sync

**Taken:** 11 November 2026, in the development watcher · **Status:** Accepted

**What.** The watcher's board panel reads `.watch/board.json`, which the
assistant writes as it reads Jira. With no credentials configured, nothing
else updates it.

**Why.** The alternative is a Jira API token on disk by default, which is a
real cost for a convenience.

**Impact.** The board panel can be stale when nobody is working, and a stale
board read as current would be worse than no board at all.

**Mitigation.** The panel header always shows how long ago it synced, so
staleness is visible rather than silent. Setting `JIRA_EMAIL` and
`JIRA_API_TOKEN` in `.env` turns on live polling for anyone who wants it.

---

### TD-13 — Nothing automated proves the Embedding API still answers

**Taken:** 11 November 2026, in ON-10 · **Status:** Open

**What.** `scripts/check_embedding_api.py` is the only thing that makes a
real request to the Embedding API, and a person has to run it by hand.
`backend/tests/test_embedding_api_check.py` covers every branch of the
script with the transport replaced, so the suite never leaves the machine.

**Why.** A real embedding request needs a paid key. Putting one in CI means
a repository secret and a bill that grows with every push, and putting one
in the default test run means teammates without a key see failures that say
nothing about their change.

**Impact.** A revoked key, a renamed model or a provider breaking change
will not show up until somebody runs the script or until the Embedding
Client (ON-41) fails at upload time with a less obvious error. The 1536
dimension width is also asserted only against our own setting, not against
what the provider actually returns, unless the script is run.

**Mitigation.** The script exists, is one command, and is named in the
README and in `.env.example` next to the key. When ON-49 builds the
pipeline, add a job that runs it only when an `EMBEDDING_API_KEY` secret is
present, so forks and teammates are unaffected and the main repository
still gets the signal.

---

## How to add an entry

Add it in the same pull request as the shortcut. An entry written later is an
entry that does not get written.

1. Take the next `TD-<n>`.
2. Add a row to the index and a section below, in ID order.
3. Fill in all four fields. They are the point of the log:

   - **What** — what was actually done, naming the file or setting, so a
     reader can find it.
   - **Why** — the pressure that made it the right call at the time. Not an
     apology; the reasoning.
   - **Impact** — what it costs us, concretely. "This is not ideal" is not an
     impact. "The only tests that prove X do not run unless someone remembers
     a flag" is.
   - **Mitigation** — what pays it back, and the ticket if there is one.

4. Set the status: `Open`, `Accepted` or `Mitigated`.

When a debt is paid, set the status to `Mitigated` and say what fixed it —
rather than deleting the entry. The Refinement Report needs the history, not
just the current state.

`backend/tests/test_technical_debt_log.py` checks the structure: every entry
has all four fields, the index and the sections agree, IDs are unique and in
order, and statuses are valid. It does not check that entries are honest —
only we can do that.
