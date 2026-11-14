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
| [TD-02](#td-02--no-ci-pipeline) | No CI pipeline | Build | Mitigated |
| [TD-03](#td-03--no-health-or-readiness-endpoint) | No health or readiness endpoint | Backend API | Accepted |
| [TD-04](#td-04--the-integration-tests-are-opt-in) | The integration tests are opt-in | Testing | Mitigated |
| [TD-05](#td-05--generated-pdfs-are-committed) | Generated PDFs are committed | Data | Accepted |
| [TD-06](#td-06--the-chroma-client-and-server-versions-are-coupled-by-hand) | The Chroma client and server versions are coupled by hand | Storage | Open |
| [TD-07](#td-07--python-314-is-not-supported) | Python 3.14 is not supported | Build | Open |
| [TD-08](#td-08--lint-configuration-sits-under-backend-but-covers-the-repository) | Lint configuration sits under `backend/` but covers the repository | Build | Open |
| [TD-09](#td-09--the-frontend-is-a-placeholder) | The frontend is a placeholder | Frontend | Open |
| [TD-10](#td-10--no-migration-tooling-for-the-main-database) | No migration tooling for the Main Database | Storage | Mitigated |
| [TD-11](#td-11--the-watcher-parses-test-output-with-regular-expressions) | The watcher parses test output with regular expressions | Tooling | Accepted |
| [TD-12](#td-12--the-jira-board-snapshot-is-only-as-fresh-as-the-last-sync) | The Jira board snapshot is only as fresh as the last sync | Tooling | Accepted |
| [TD-13](#td-13--nothing-automated-proves-the-embedding-api-still-answers) | Nothing automated proves the Embedding API still answers | AI Chatbot Module | Open |
| [TD-14](#td-14--the-token-gallery-is-kept-out-of-the-build-by-convention) | The token gallery is kept out of the build by convention | Frontend | Mitigated |
| [TD-15](#td-15--the-pipeline-has-no-deployment-stage) | The pipeline has no deployment stage | Build | Accepted |
| [TD-16](#td-16--every-components-css-ships-used-or-not) | Every component's CSS ships, used or not | Frontend | Accepted |
| [TD-17](#td-17--citationchip-is-a-button-that-does-nothing-yet) | CitationChip is a button that does nothing yet | Frontend | Accepted |
| [TD-18](#td-18--the-session-is-a-development-stub-and-a-refresh-signs-you-out) | The session is a development stub and a refresh signs you out | Frontend | Mitigated |
| [TD-19](#td-19--a-login-token-cannot-be-withdrawn-once-issued) | A login token cannot be withdrawn once issued | Backend API | Accepted |
| [TD-20](#td-20--nothing-limits-failed-login-attempts) | Nothing limits failed login attempts | Backend API | Mitigated |
| [TD-21](#td-21--auth-check-guards-routes-not-rows) | Auth Check guards routes, not rows | Backend API | Open |
| [TD-22](#td-22--nothing-inspects-what-is-inside-an-uploaded-document) | Nothing inspects what is inside an uploaded document | Backend API | Mitigated |
| [TD-23](#td-23--the-20-second-timeout-stops-the-wait-not-the-call) | The 20-second timeout stops the wait, not the call | AI Chatbot Module | Accepted |
| [TD-24](#td-24--the-login-token-is-readable-by-script-on-the-page) | The login token is readable by script on the page | Frontend | Accepted |
| [TD-25](#td-25--the-admin-upload-page-uses-one-of-its-three-endpoints) | The Admin Upload Page uses one of its three endpoints | Frontend | Open |
| [TD-26](#td-26--an-upload-cannot-be-cancelled) | An upload cannot be cancelled | Frontend | Open |

Status is **Open** (we intend to pay it back), **Accepted** (we have decided
to live with it, and the entry says why), or **Mitigated** (paid back; kept
for the record, with what fixed it).

---

### TD-01 — The Mock LLM is the default provider

**Taken:** 11 November 2026, in ON-9 · **Status:** Open · **Ticket:** ON-18

**What.** `LLM_PROVIDER` defaults to `mock`. No real language model is
wired in. *Updated 14 November 2026, ON-44:* the `LLMProvider` interface
now exists with the `generate(prompt)` the contracts fix, and the Mock LLM
implements it — so the shape of the seam is settled and only the production
implementation behind it is missing. `"real"` is deliberately not a
selectable name until ON-18 lands, because a name that resolves to nothing
is better than one that resolves to a stub nobody notices.

**Why.** Backend and frontend work could not wait for a model to be chosen,
and the design requires that the Mock LLM stays selectable so CI and
teammates without the model can still run the system.

**Impact.** Nothing exercises the real `generate(prompt)` path, and answer
quality is entirely unmeasured — no claim about it is supportable.

The second half of this used to read that the Gateway's timeout, JSON check
and provider-error handling were untested against anything that could
actually fail. ON-44 changed that: the Mock LLM can be told to be slow, to
raise, or to return something that is not JSON, which are exactly the three
conditions the contracts say produce the HR fallback. They are testable
now. What remains untested is how a *real* model fails, which is rarely how
a mock does.

**Mitigation.** ON-18 selects a real provider and wires it behind the same
interface; the Mock LLM remains selectable by configuration. ON-24 then
measures answer quality against the evaluation set. Until then, no claim
about answer quality is supportable.

---

### TD-02 — No CI pipeline

**Taken:** 11 November 2026, in ON-9 · **Status:** Mitigated · **Ticket:** ON-49

**What.** Tests and lint run only on developer machines. Nothing runs
automatically on a pull request.

**Why.** ON-49 builds the pipeline and was blocked by the scaffold in ON-9.

**Impact.** A pull request can merge with failing tests; nobody would know.
The board rule that a ticket is Done when "CI is green" currently degrades to
"the author ran the tests". Development happens on Windows while CI will run
Linux, so a Windows-only assumption could reach `main` unnoticed — the kind
of thing that surfaces at the worst moment.

**Mitigation.** Paid back in ON-49. `.github/workflows/ci.yml` runs on every
push and every pull request: a backend job (ruff, ruff format, the unit
tests), a frontend job (oxlint, vitest, `tsc -b && vite build`) and an
integration job with PostgreSQL and ChromaDB service containers. Both jobs
run on Linux, which is the point — development happens on Windows.

**Left over.** Nothing enforces that the checks have actually run before a
merge. Branch protection requiring the three jobs is a repository setting,
not a file in the repository, so it is Jared's to turn on; until he does, the
pipeline reports but does not block. See also TD-15: there is no deployment
stage.

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

**Taken:** 11 November 2026, in ON-9 · **Status:** Mitigated · **Ticket:** ON-49

**What.** `backend/pyproject.toml` sets `addopts = "-m 'not integration'"`, so
the tests that talk to PostgreSQL and ChromaDB are deselected by default. They
run only with `pytest -m integration`.

**Why.** It keeps the default suite fast and lets a teammate run the tests
without Docker running.

**Impact.** The only tests that prove the backend can reach its stores do not
run unless someone remembers the flag. They can break and stay broken without
anyone noticing, which is the worst property a test can have.

**Mitigation.** Paid back in ON-49. The `integration` job in
`.github/workflows/ci.yml` starts PostgreSQL and ChromaDB as service
containers on the image versions `docker-compose.yml` pins, applies the
migration with `alembic upgrade head`, and runs `pytest -m integration`. They
stay deselected locally, so the fast suite is still fast and Docker is still
optional on a developer machine, but they can no longer break unnoticed.

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

**What.** Every page is a placeholder. As of ON-65 the frontend has design
tokens, a component library, an application shell, routing and role guards —
but no page does anything, because none of them exists yet and there is no
API client to talk to the backend with.

*Updated 12 November 2026.* When this entry was written in ON-9 it said
"no routing, no API client, no design tokens and no styling beyond a base
font". Three of those four have landed; the API client has not, and that is
the one the sentence below about an unproven path depends on.

**Why.** ON-9 was scaffolding only. The interface is epic ON-62, which builds
tokens (ON-63), then shared components (ON-64), then the app shell (ON-65),
then the pages — deliberately in that order.

**Impact.** Nothing has yet gone from a click in the browser to a row in the
Main Database. The API client (ON-38) does not exist, so no page can talk to
the backend, and the whole frontend-to-backend path is unproven — including
the error shapes the contracts define, which no page has ever had to render.
A production build of the frontend currently has no way to sign in at all,
since the only sign-in is the development stub (see TD-18).

**Mitigation.** ON-38 next, which brings the login page and the API client
together and proves one path end to end, then the remaining pages. The
placeholder each route renders names the ticket that replaces it, and the
quality rule is that placeholder content goes as soon as the real thing
exists.

---

### TD-10 — No migration tooling for the Main Database

**Taken:** 11 November 2026, in ON-9 · **Status:** Mitigated · **Ticket:** ON-11

**What.** `backend/app/db/session.py` creates a SQLAlchemy engine, a session
factory and a declarative `Base`. There are no models, and no decision has
been made about how schema changes will be applied.

**Why.** The schema is ON-11, which was blocked by the scaffold. Choosing
migration tooling before there was a single table would have been guessing.

**Impact.** This is the entry most likely to bite after the alpha. The first
schema change against a database holding data has no upgrade path, and
"recreate the database" stops being acceptable the moment anyone has
uploaded documents they care about.

**Mitigation.** Paid back in ON-11, in the same pull request that created the
schema rather than in a later one. Alembic owns the tables: `alembic upgrade
head` is the setup step, `backend/migrations/versions/` is the history, and
every revision has a working `downgrade`. A test fails if the models and the
migrations disagree, so the gap this entry warned about — a schema that
exists in code and not in the database — is now a failing test rather than a
discovery in production.

**Left over.** Nothing enforces that a migration is *safe* on a table that
already holds rows: adding a `NOT NULL` column without a default still locks
and fails. That is a review question until there is data worth protecting.

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

---

### TD-14 — The token gallery is kept out of the build by convention

**Taken:** 11 November 2026, in ON-63 · **Status:** Mitigated · **Ticket:** ON-49

**What.** The development token gallery is excluded from the production
bundle by two source-level conventions rather than by a check on the build
output: the guard in `App.tsx` must be written as the literal
`import.meta.env.DEV && ...`, and `TokenGallery.tsx` must import its
stylesheet with `?inline`. Tests assert both strings are present in the
source. Nothing inspects `dist/`.

**Why.** Running `vite build` inside the unit test suite would add several
seconds to every `npm test`, and the frontend has no CI job yet (ON-49) where
a slower, build-level check would be free.

**Impact.** The tests prove the two conventions are still written down, not
that the bundle is clean. A third way to leak the gallery — a new import of
it from shipped code, say — would pass every test. The leak is small (about
2 kB of CSS and 4 kB of JavaScript) and is a development page, not a
security boundary, but it is dead weight in a build that is meant to be the
alpha.

**Verified by hand on 11 November 2026:** after `npm run build`, neither
`gallery-swatch` nor any gallery string appears in `dist/assets/*.js` or
`dist/assets/*.css`, and the stylesheet dropped from 6.25 kB to 4.18 kB once
the `?inline` import replaced the plain one.

**Mitigation.** Paid back in ON-49, one ticket later. The frontend job builds
and then greps `dist/` for `gallery-swatch`, failing the run if it is there.
That is a check on the artefact that actually ships, so it catches a third
way of leaking the gallery as well as the two the source-level tests know
about.

---

### TD-15 — The pipeline has no deployment stage

**Taken:** 11 November 2026, in ON-49 · **Status:** Accepted · **Ticket:** ON-49

**What.** ON-49 asks for build, automated tests and deployment. The pipeline
does the first two. It ends by uploading the built frontend as a run
artefact; nothing is deployed anywhere.

**Why.** There is no environment to deploy to. The alpha is run locally from
the README, the backend needs PostgreSQL and ChromaDB, and no hosting has
been chosen or paid for. A deploy step pointing at nothing would be a green
check that means nothing, which is worse than an absent one.

**Impact.** "CD" in the pipeline's name is aspirational. Nobody can install
the alpha from a URL; a reviewer follows the README. The build artefact is
the closest thing to a release and expires after 7 days.

**Mitigation.** Accepted for the alpha. If a host is chosen later, the
frontend job already produces the artefact a deploy step would publish, and
the backend would need a container image, which does not exist yet either.

---

### TD-16 — Every component's CSS ships, used or not

**Taken:** 12 November 2026, in ON-64 · **Status:** Accepted · **Ticket:** ON-65

**What.** Each component imports its own stylesheet for the side effect
(`import './Button.css'`). Rollup has to keep a side-effect import even when
it drops the module that made it, so a component's CSS is in the bundle from
the moment the component exists — whether or not any page renders it. Right
now no page does: the shell is ON-65 and the pages come after it, so the
alpha build carries about 11 kB of CSS for components nothing uses yet.

**Why.** The alternative is the `?inline` trick the development galleries
use, which turns the stylesheet into a string the component injects into a
`<style>` tag. That works for one development page rendered once. For a
library it means every instance of a component carrying its own stylesheet
into the DOM, styles arriving after first paint, and no single stylesheet
for the browser to cache — a worse trade for a saving that disappears as
soon as the pages exist.

**Impact.** Small and temporary while the pages are built. The lasting part
is that a component which is *never* used keeps its CSS in the bundle for
good, and nothing says so: the size test checks what is in a stylesheet, not
whether anyone needs it.

**Mitigation.** Self-resolving as ON-65 and the page tickets consume the
library. If a component turns out to be unused once the pages are done, the
honest fix is to delete it rather than to tune the bundler. The CI job
already greps `dist/`, so a check for a component class that appears in the
CSS and nowhere in the JavaScript could be added there cheaply if this ever
matters.

---

### TD-17 — CitationChip is a button that does nothing yet

**Taken:** 12 November 2026, in ON-64 · **Status:** Accepted · **Ticket:** ON-48

**What.** ON-64 asks for the citation chip to be focusable. It is rendered
as a `<button>` with an optional `onClick`, and until the chat page wires
that handler, a keyboard user can tab to it, press it, and get nothing.

**Why.** The alternative was a `<span tabindex="0">`, which is worse: it
takes the same keystroke and announces nothing about what it is. A button at
least says it is pressable, and the chip is going to become pressable — ON-48
hangs "show me that section" off it.

**Impact.** One focus stop per citation that leads nowhere, in the window
between this ticket and ON-48. Up to five of them under an answer, since
retrieval returns the top five sections.

**Mitigation.** ON-48 supplies the handler. If that slips past the alpha,
the chip should stop being a button and become plain text until it does
something, which is a one-line change in `CitationChip.tsx`.

---

### TD-18 — The session is a development stub and a refresh signs you out

**Taken:** 12 November 2026, in ON-65 · **Status:** Mitigated · **Ticket:** ON-38

**What.** There is no real sign-in. The login page offers two buttons —
Continue as Employee, Continue as HR administrator — that put a made-up
session into React state, and the shell reads the role from there. The
session is in memory only, so a page refresh signs you out. In a production
build the buttons are gone and there is no way in at all.

**Why.** The epic's build order puts the shell before the pages, and the
shell is a role-based layout: it cannot be built, looked at or tested
without a role to drive it. The alternative was to block ON-65 on ON-36 and
ON-38, which would have stalled the whole UI sequence behind the Auth
Service. The ticket itself says to use a stubbed session context until
ON-38 lands.

Keeping the session in memory is the other half of the same decision. Where
a token is kept, and for how long, is ON-38's call; writing a second answer
here would mean either changing it later or quietly keeping both.

**Impact.** Anyone trying the alpha from a build cannot sign in. In
development, a refresh during a long session costs you your place. The guards
are real but they guard a fiction: until ON-38, nothing has ever checked a
password, and until Auth Check sees a token, nothing has enforced a role
anywhere that matters.

**Mitigation.** *14 November 2026, ON-38:* paid back, and not quite the way
this entry predicted.

The real form is in, against `POST /api/auth/login`. The two development
buttons were **deleted** rather than left behind the `import.meta.env.DEV`
literal: a password-free way in that only works in development is still a
password-free way in that somebody eventually ships, and there is now a real
Auth Service to sign in against. The CI grep for `"Continue as Employee"`
went with them, and the test that asserted the literal was present now
asserts the opposite — that nothing in the login page skips the password.

The refresh is fixed too, by `sessionStorage` rather than by the in-memory
session this entry described. What that costs is **TD-24**.

One prediction here was wrong and worth noting: this entry said ON-38 would
map the login response onto "the same `Session`". It did not. The endpoint
returns the token and nothing else, so the session is now *derived* from the
token rather than stored next to it — one piece of state instead of two,
because two can disagree, and the way they disagree is an interface showing
somebody as signed in while the header carries a token the server has
stopped accepting.

---

### TD-19 — A login token cannot be withdrawn once issued

**Taken:** 12 November 2026, in ON-36 · **Status:** Accepted · **Ticket:** ON-14

**What.** Login tokens are signed JWTs carrying the user id, email, name and
role. The server keeps no record of them, so there is no list to remove one
from: a token is valid until it expires, even if the account it names is
deleted, has its role changed, or has its password reset.

**Why.** The Interface Contracts say the Main Database holds six things —
users, documents, sections, chat logs, feedback and escalations — and a
sessions table is not one of them. Storing issued tokens would mean adding a
concept the design does not name, and `docs/` is the source of truth. A
stateless token also lets Auth Check answer "who is this and may they" from
the request alone, with no database round trip on every call, which is what
the architecture diagram shows at step 2.

**Impact.** A leaked token works until it expires. Revoking access in a
hurry means rotating `AUTH_SECRET_KEY`, which signs every holder out at
once, not just the one. A role change does not take effect until the person
next logs in — relevant because the role in the token is what Auth Check
reads, so somebody promoted to HR administrator keeps seeing the Employee
navigation until their token expires.

**Mitigation.** The token's life is the only limit, so it is short:
`AUTH_TOKEN_TTL_MINUTES` defaults to 720, one working day. The signing key
is server-side only, never reaches the browser bundle, and has no committed
default — in production the backend refuses to start without one. Rotating
it is the break-glass revocation, and it is one environment variable. If
per-token revocation turns out to be needed after the alpha, the smallest
honest version is a `jti` claim and a short deny list, which is a change to
ask about rather than to make quietly.

---

### TD-20 — Nothing limits failed login attempts

**Taken:** 12 November 2026, in ON-36 · **Status:** Mitigated · **Ticket:** ON-37

**What.** As first written, the Auth Service would check as many passwords
as it was asked to: no attempt counter, no lockout, no delay that grows,
and no rate limit in front of the endpoint. ON-37 added one the same day —
see the mitigation, which also says what the limit does *not* cover.

**Why.** ON-36 builds the Auth Service and ON-37 the endpoint; a rate limit
belongs at the edge, in front of the route, and neither the architecture
diagram nor the Interface Contracts name a component that does it. Inventing
one here would have meant inventing an endpoint's behaviour inside a service
ticket.

**Impact.** An attacker who can reach the API can guess passwords as fast as
the server will hash them. scrypt is what makes that expensive rather than
free — roughly a quarter of a second of one core per attempt, so a few
hundred guesses a minute per core rather than millions — but expensive is
not prevented, and the same cost is also a way to exhaust the server's CPU
by asking it to hash.

**Mitigation.** *12 November 2026, ON-37:* `POST /api/auth/login` now
limits failures to ten per address and ten per client in a fifteen-minute
sliding window, checked **before** any password is hashed — so a refused
request costs about 3 ms instead of 370 ms, which answers the second half
of the impact above as well as the first. A success clears both counts. The
number of keys tracked is capped, because a limiter that grows a dictionary
per attempted address is itself a way to exhaust the server's memory.

Three things it still does not do, and they are the reason this entry is
worth reading rather than closing. The count lives in the process, so two
uvicorn workers each allow the full ten and a restart forgets everything —
run one worker for the alpha. Behind a proxy, `request.client.host` is the
proxy, so every caller shares one client bucket; `X-Forwarded-For` is
deliberately not trusted, because anyone can set it and trusting it would
let an attacker hand themselves a fresh allowance per request. And a
distributed attempt from many addresses still gets ten guesses each. The
shape of the fix for all three is the same code against Redis plus a
trusted-proxy setting, which is a change to ask about rather than to make
quietly.

scrypt's cost remains the floor underneath all of it: the same parameter
that protects a stolen password table also prices an online guess.

---

### TD-21 — Auth Check guards routes, not rows

**Taken:** 14 November 2026, in ON-14 · **Status:** Open · **Ticket:** ON-16

**What.** Auth Check answers one question: may *this role* reach *this
endpoint*. It does not ask whether this particular person may see this
particular record. `GET /api/escalations` is open to both roles because the
contracts put both the HR Inbox Page and the Chat Page on it — so as things
stand, any employee's token reaches the endpoint that lists escalations,
and nothing at the door distinguishes their own from everybody else's.

**Why.** The architecture diagram puts Auth Check in front of the API, where
it sees a method and a path and no data. Deciding which rows come back means
reading them first, which happens inside the endpoint. Teaching the door to
reason about rows would mean either querying the database twice or moving
the endpoint's logic into the door, and both are worse than the gap.

**Impact.** Until the escalation endpoints filter, an employee who calls
`GET /api/escalations` directly — not through the Chat Page, which will ask
only for their own — would see other employees' questions to HR. Those are
exactly the questions somebody was uncomfortable enough about to escalate.
Nothing in the alpha surfaces this in the interface, which makes it the kind
of gap that is found by a reviewer with curl rather than by a user.

**Mitigation.** ON-16 builds `GET /api/escalations` and owns the filter: an
Employee's token gets their own escalations, an HR administrator's gets all
of them, decided from `claims.user_id` and `claims.role` which Auth Check
has already verified and left on the request. ON-21's HR Inbox reads the
same endpoint. Until that lands the endpoint does not exist at all, so the
gap is real but not yet reachable — which is the one good reason to write it
down now rather than discover it later.

---

### TD-22 — Nothing inspects what is inside an uploaded document

**Taken:** 14 November 2026, in ON-39 · **Status:** Mitigated · **Ticket:** ON-40

**What.** An upload is checked three ways — it begins `%PDF-` or contains no
NUL bytes, it is not empty, and it is under the size limit — and then it is
written to File Storage as it arrived. Nothing scans it for malware, and
nothing bounds what the file will cost to parse. ON-40 then hands it to a
PDF library.

**Why.** The magic-byte check is what stops the mistake this project will
actually make — somebody uploading a .docx renamed to .pdf, which would be
stored happily and then fail silently at extraction. Scanning is a different
problem, needs a scanner the team does not have, and is not something the
architecture names. The endpoint is HR-only, so the people who can reach it
are the two or three administrators the system is for.

**Impact.** A PDF crafted to be expensive to parse — deeply nested objects,
a compression bomb — is a 10 MB upload that could cost far more than 10 MB
of memory when ON-40 opens it, in-process, with no timeout. That is a denial
of service available to anybody holding an HR administrator token, which for
the alpha means anybody holding the seeded HR password.

**Mitigation.** *14 November 2026, ON-40:* the other half is in. Extraction
stops at three bounds and says which one it hit — `PDF_MAX_PAGES` (200),
`EXTRACTION_MAX_CHARACTERS` (one million) and `EXTRACTION_TIMEOUT_SECONDS`
(15), the last checked **per page** rather than once at the end, because the
point is to stop doing the work rather than to find out afterwards that it
was done. A page that will not parse is skipped with a log line instead of
failing the document; a PDF that will not open at all, or that has no text
layer, is a `422` and the upload is undone.

What is still true is the first sentence of **What**: nothing scans an
upload for malware, and nothing will before the alpha. The bound is on what
parsing may cost, not on what the file may contain. The endpoint remains
HR-only and the alpha is not on the public internet, which is what makes
that acceptable rather than merely convenient.

---

### TD-23 — The 20-second timeout stops the wait, not the call

**Taken:** 14 November 2026, in ON-45 · **Status:** Accepted · **Ticket:** ON-18

**What.** `LLMProvider.generate(prompt)` is an ordinary blocking call, and
Python gives no way to interrupt one from outside. The LLM Gateway runs it
on a daemon thread and stops waiting after twenty seconds — but the thread
carries on until the provider returns on its own. A provider that never
returns leaves a thread behind for the life of the process.

**Why.** The contracts fix the twenty seconds and fix `generate(prompt)` as
the whole interface, so the provider is not given a timeout to honour and
could not be trusted with one anyway: a provider that is not answering is
not going to enforce a limit on itself. Stopping the wait is the part that
matters to the employee, and it is the part that can be done from here.

**Impact.** Each timed-out request costs a thread until its provider
returns. Twenty of them against a wedged local model is twenty threads, and
if the model is wedged because it is out of VRAM they will not return.
Nothing bounds how many can accumulate. It is a slow leak rather than a
crash, and the thing it would eventually exhaust is memory. The daemon flag
at least means a hung provider cannot stop the backend exiting, which an
executor-managed thread would have done.

**Mitigation.** The real fix belongs to whoever writes the Real LLM Client
(ON-18): an HTTP client with its own socket and read timeouts, set below the
Gateway's twenty seconds, so the call *returns* rather than merely being
abandoned. Then the Gateway's limit becomes the backstop it should be
instead of the only line of defence. Until then the Mock LLM always
returns, so nothing in the alpha leaks a thread unless a real provider is
wired in.

A note on how this was found: the first version used
`with ThreadPoolExecutor(...)`, whose `__exit__` calls `shutdown(wait=True)`
— so the pool joined the very thread the timeout had just given up on, and
the Gateway returned only once the provider did. The limit was not a limit,
and it read as correct. Only a test that measured the wall clock noticed.

---

### TD-24 — The login token is readable by script on the page

**Taken:** 14 November 2026, in ON-38 · **Status:** Accepted · **Ticket:** none

**What.** The login token is kept in `sessionStorage` and attached to each
request as an `Authorization: Bearer` header. Anything running as script on
the page can read it — so a cross-site scripting hole anywhere in the
frontend is also a session theft, for as long as the token lasts.

**Why.** It was a choice between three imperfect options. In memory only is
what ON-65 shipped and TD-18 is the complaint about it: a refresh signs you
out, which during a demo means losing your place whenever somebody reloads.
`localStorage` fixes the refresh and also survives closing the browser, on a
shared machine, until the token expires. `sessionStorage` fixes the refresh
and dies with the tab, which is the narrowest window that addresses the
actual complaint.

The textbook answer is an `httpOnly` cookie the page's JavaScript cannot
read. That needs the backend to set and clear cookies, and it brings CSRF
protection into scope — a second mechanism, on a deadline, for a demo that
is not on the public internet. It is also a slightly different reading of
the contracts, which say the API Client "sends requests with the login
token": a header is the natural reading of that sentence and a cookie is
not.

**Impact.** One XSS anywhere in the React application — a dependency, a
rendered-as-HTML string, a future page that interpolates a document name —
gives up a working session. The token carries the holder's role, so an HR
administrator's stolen token is HR access to upload and delete documents and
to read every escalation. There is no revocation (TD-19), so the thief has
it until it expires.

**Mitigation.** The window is the mitigation, and it is a real one rather
than a comforting one: the token lasts one working day (TD-19) and the
storage dies with the tab, so a token cannot be picked up from a machine
somebody walked away from once the browser is closed. React escapes
interpolated text by default, and nothing in the frontend uses
`dangerouslySetInnerHTML` — worth keeping true, and worth a lint rule if it
ever stops being obvious. Nothing is stored except the token: a test asserts
the password appears in no storage, no URL and no rendered markup.

If this moves past an alpha, the cookie is the answer, and it should be
decided alongside TD-19's revocation rather than separately — the two are
the same conversation about what a session is.

---

### TD-25 — The Admin Upload Page uses one of its three endpoints

**Taken:** 14 November 2026, in ON-42 · **Status:** Open · **Ticket:** ON-16

**What.** The Interface Contracts give the Admin Upload Page three
endpoints: `POST /api/documents`, `GET /api/documents` and
`DELETE /api/documents/{id}`. The page built in ON-42 uses the first one.
There is no list of what has been uploaded and no way to remove anything,
because neither endpoint exists on the server yet — only POST is
implemented.

**Why.** Listing and deleting are ON-16, which is blocked behind ON-15.
Writing the client functions now would mean shipping two calls that return
404, which is worse than their absence: a function that exists looks
callable, and the next person to need a document list would find one and
wire a page to it. So `api/documents.ts` has one function and says in its
own header why.

**Impact.** An HR administrator can upload a document and is told what
happened to it, and then has no way to see it again. Uploading the same
file twice produces two documents with no indication that the first one is
already there, and nothing in the interface can undo either. For the alpha
the upload is the demonstrable half of U1 to U4; for anybody actually
curating a policy library it is half a feature.

**Mitigation.** None in the interface, deliberately — a list the page
assembled from its own successful uploads would be a list that empties on
refresh and disagrees with the database, which is a worse answer than no
list. The server is the only thing that knows what documents exist, and it
will say so when ON-16 lands. Until then `scripts/` and `psql` are how
somebody checks, which is acceptable for a development database and not
acceptable for a user.

---

### TD-26 — An upload cannot be cancelled

**Taken:** 14 November 2026, in ON-42 · **Status:** Open · **Ticket:** none

**What.** `uploadWithProgress` takes an `AbortSignal` and honours it: it
aborts the request, stops listening, and rejects with an `AbortError` the
same way `fetch` does. The page passes no signal and offers no Cancel
button. So a large upload runs to completion whether or not anybody still
wants it, and navigating away from the page mid-upload leaves the request
going and its answer discarded.

**Why.** The cancel path is the easy half; deciding what a cancelled
upload *means* is not. The server does U2 and U3 in one request — it saves
the file, extracts the text and writes the sections before it answers — so
aborting after the last byte has gone out does not stop any of that. It
only stops this page hearing the result. A Cancel button that leaves a
document saved and indexed, while telling the person their upload was
cancelled, is a worse lie than no button. Doing it properly needs either a
`DELETE` to undo it (TD-25, ON-16) or a server that treats a dropped
connection as a reason to discard the upload, and neither is in this
ticket.

**Impact.** Somebody who picks the wrong 40 MB file waits for it. On a slow
connection that is a real wait with no way out but a browser reload, which
has the same problem — the bytes already sent still arrive, and the
document may well be stored. The capability is tested and present in the
transport, so the gap is in the page, not in the plumbing.

**Mitigation.** The size limit is the practical bound: the server refuses
anything over `MAX_UPLOAD_BYTES` and the browser stops sending as soon as
it is told to, so the worst wait is bounded by that limit rather than by
the file somebody chose. The abort path is covered by tests
(`api/upload.test.ts`) rather than left to rot, so wiring a button is a
small change when the question above has an answer — which it will have
once `DELETE /api/documents/{id}` exists.
