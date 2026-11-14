# OnboardAI

[![CI](https://github.com/jkwakyi/OnboardAI/actions/workflows/ci.yml/badge.svg)](https://github.com/jkwakyi/OnboardAI/actions/workflows/ci.yml)

An AI employee onboarding assistant. Employees ask questions in a chat page
and get answers with citations drawn from HR documents an HR administrator
has uploaded. When nothing in the documents matches well enough, the answer
is an HR fallback rather than a guess, and the employee can send the question
to the HR Inbox.

Built for CMSC 495 by Brad Campos, Jared Ahenkora-Kwakyi and Muhammed Ayday.

## Architecture

| Piece | Technology |
| --- | --- |
| Frontend | React + TypeScript (Vite) |
| Backend API | FastAPI — one application, modular monolith |
| Main Database | PostgreSQL — users, documents, sections, chat logs, feedback, escalations |
| Vector Database | ChromaDB — section embeddings |
| Embedding API | OpenAI `text-embedding-3-small`, called over HTTPS |
| LLM | Behind an `LLMProvider` interface; Mock LLM or a real provider |

The design is fixed and lives in [`docs/`](docs/). The Interface Contracts are
the source of truth for endpoints, fields and error formats.

## Prerequisites

- **Python 3.12 or 3.13** (3.14 is not yet supported by all dependencies)
- **Node.js 22.19 or newer** (jsdom's `undici` refuses to load on 20; CI runs 24)
- **Docker Desktop**, for PostgreSQL and ChromaDB

## Setup

Clone and configure:

```bash
git clone https://github.com/jkwakyi/OnboardAI.git
cd OnboardAI
cp .env.example .env
```

`.env` is ignored by Git and never committed. The defaults in `.env.example`
match the Docker Compose services below, so it works unedited for local
development.

### 1. Start the databases

```bash
docker compose up -d
```

This starts PostgreSQL on port **5432** and ChromaDB on port **8001**, each
with a named volume so your data survives a restart. Check they are healthy:

```bash
docker compose ps
```

Stop them with `docker compose down`, or `docker compose down -v` to delete
the data as well.

### 2. Backend

From the repository root:

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment — **macOS/Linux**:

```bash
source .venv/bin/activate
```

**Windows (PowerShell)**:

```powershell
.venv\Scripts\Activate.ps1
```

Then install and run:

```bash
pip install -e ".[dev]"
```

### 3. Create the Main Database tables

Still in `backend`, with the databases running:

```bash
alembic upgrade head
```

That creates the six tables the system uses — users, documents, sections,
chat logs, feedback and escalations. It is safe to run again: Alembic records
which migrations have been applied, so a second run does nothing.

Run it again after every `git pull` that adds a migration. To see what it
would do without touching the database, use `alembic upgrade head --sql`; to
undo the most recent migration, `alembic downgrade -1`.

Adding or changing a table is a migration, not an edit to a live database.
Change the models in `backend/app/db/models.py`, then:

```bash
alembic revision --autogenerate -m "what you changed"
```

Read the generated file before committing it — autogenerate is a draft, not
an authority. `pytest` fails if the models and the migrations disagree.

Now start the API:

```bash
uvicorn app.main:app --reload
```

The API is at <http://localhost:8000> and its generated documentation at
<http://localhost:8000/docs>. On startup the log says whether the Main
Database and Vector Database are reachable; if either is not, start the
stack with `docker compose up -d`.

### 4. Frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm install
npm run dev
```

The app is at <http://localhost:5173>.

There is no sign-in yet: the Auth Service is ON-36 and the login form is
ON-38. Until then the login page offers two buttons that sign you in as an
Employee or an HR administrator so the interface can be used. They exist in
`npm run dev` only and are not in a production build.

All styling comes from the design tokens in
`frontend/src/styles/tokens.css` — no component contains a colour or a
measurement. Pages are built from the shared components in
`frontend/src/components/`, inside the app shell in `frontend/src/shell/`.
Two development pages show the parts on their own:
<http://localhost:5173/#tokens> for the tokens and
<http://localhost:5173/#components> for every component in every state.
All of it, and the measured contrast ratios, are documented in
[`frontend/README.md`](frontend/README.md#design-tokens).

### 5. Embedding API key

The assistant turns document sections and questions into vectors through a
hosted Embedding API. The provider is **OpenAI**, the model is
`text-embedding-3-small`, and it returns **1536** dimensions — the width the
ChromaDB collection is built for.

Create a key at <https://platform.openai.com/api-keys> and put it in your own
`.env` at the repository root:

```
EMBEDDING_API_KEY=your-key-here
```

The key is server-side only. It never goes in `frontend/.env`, never in a
`VITE_`-prefixed variable, and never in a commit: `.env` is ignored by Git.
Then prove it works:

```bash
python scripts/check_embedding_api.py
```

That makes one real request and reports the vector width and how long it
took. It prints nothing that could leak the key. Run it after creating the
key, and again whenever the provider, model or key changes.

The rest of the stack runs without a key — only the embedding path needs it.

### 6. Sign-in accounts

Two synthetic accounts, one per role, so you can see both halves of the
application. Pick a password for each in your own `.env`:

```
SEED_EMPLOYEE_PASSWORD=
SEED_HR_PASSWORD=
```

There is deliberately no default. A password written into a tracked file is
a password every checkout of this repository shares, so `.env.example` names
the two variables and leaves them empty — and a test fails if a value ever
appears next to one. Then create the accounts:

```bash
python scripts/seed_accounts.py
```

| Account | Address | Role |
| --- | --- | --- |
| Alex Rivera | `employee@onboardai.example` | Employee |
| Jordan Blake | `hr@onboardai.example` | HR administrator |

Both addresses end in `.example`, which RFC 2606 reserves, so a demo account
can never reach a real mailbox. Run the script again any time to reset the
accounts — it resets rather than failing, which is what you want after
dropping the database or forgetting a password. It never prints a password,
and `python scripts/seed_accounts.py --list` shows what it would create
without touching the database.

Logging in returns a signed token that lasts one working day. You can also
set a signing key, which keeps you signed in across backend restarts:

```
AUTH_SECRET_KEY=generate-your-own
```

Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Leave it unset in development and the backend signs with a random key made
at startup and says so in the log; set `ONBOARDAI_ENV=production` and it
refuses to start without one. Like the embedding key, it is server-side
only: never in `frontend/.env`, never in a `VITE_` variable, never in a
commit.

Passwords are stored as scrypt hashes with the cost parameters written into
each hash, so the cost can be raised later without locking anybody out — see
the module docstring in
[`backend/app/services/auth/passwords.py`](backend/app/services/auth/passwords.py)
for why these parameters.

With the API running, logging in looks like this:

```bash
curl -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{"email":"employee@onboardai.example","password":"the-one-you-chose"}'
```

The response is the token and nothing else, which is what the Interface
Contracts say comes back. Everything the Login Page needs to render — the
holder's name and role — is already in the token's claims, and Auth Check
(ON-14) is what enforces the role on every later request.

Send that token back on every other request:

```bash
curl http://localhost:8000/api/documents -H "Authorization: Bearer $TOKEN"
```

Auth Check sits in front of every endpoint under `/api` and checks the token
and the role before the endpoint runs — `backend/app/api/auth_check.py` has
one table naming which roles may reach each of the nine endpoints, and an
endpoint missing from it is refused rather than allowed. No token is a
`401`; an expired one is a `401` saying the session ended; the right token
with the wrong role is a `403`. Only `POST /api/auth/login` is public. What
Auth Check deliberately does *not* decide is which records come back, which
is
[TD-21](TECHNICAL-DEBT.md#td-21--auth-check-guards-routes-not-rows).

`/docs` has an **Authorize** button: paste a token there and the generated
documentation will send it for you.

### Uploading a document

```bash
curl -X POST http://localhost:8000/api/documents -H "Authorization: Bearer $TOKEN" -F "file=@data/handbook/benefits.pdf"
```

HR administrators only. A PDF or a TXT, up to `MAX_UPLOAD_BYTES` (10 MB by
default); the original is kept in `FILE_STORAGE_DIR` under a name the server
generates, and the name you uploaded is kept in the database for display and
never used to build a path. What the bytes say beats what the request
declared: a file called `handbook.pdf` that does not begin `%PDF-` is
refused rather than stored and discovered later.

`415` for anything that is not a PDF or TXT, `413` for one over the limit,
`400` for an empty one.

The text is then extracted and split into **sections** — the unit the rest
of the assistant is built on: a section is what gets a vector, what
retrieval returns five of, and what a citation points at. The split follows
the document's own headings where it has them, because whoever wrote it
divided it better than any rule could; a section too long for one retrieval
result is split again at paragraph boundaries, keeping its heading so the
citation still names where it came from.

A document nothing can be read from is a **`422`** and the upload is undone
— no row, no file, no sections. The case that matters is a scanned PDF: it
needs text recognition before it can answer anything, and an HR
administrator should hear that at the moment they upload it rather than
discover later that the assistant never cites it.

Reading is bounded three ways, which is the other half of
[TD-22](TECHNICAL-DEBT.md#td-22--nothing-inspects-what-is-inside-an-uploaded-document):
`PDF_MAX_PAGES`, `EXTRACTION_MAX_CHARACTERS` and
`EXTRACTION_TIMEOUT_SECONDS`, the last checked per page. Turning the
sections into vectors is ON-41.

Bad credentials are a `401` with the same message whichever way they are
wrong; a malformed body is a `422`, including one carrying a field the
contracts do not define. Ten failures from one address, or from one client,
inside fifteen minutes earn a `429` with a `Retry-After` header — checked
before any password is hashed, so a refused request is cheap. The limit
lives in the process, so run **one** uvicorn worker for the alpha; what it
does and does not cover is
[TD-20](TECHNICAL-DEBT.md#td-20--nothing-limits-failed-login-attempts), and
the fact that a token cannot be withdrawn once issued is
[TD-19](TECHNICAL-DEBT.md#td-19--a-login-token-cannot-be-withdrawn-once-issued).

### Which language model answers

Nothing downloads a model and nothing needs a key:

```
LLM_PROVIDER=mock
```

The design puts an `LLMProvider` interface in front of the model, with the
one method the contracts fix — `generate(prompt)`. The **Mock LLM**
implements it and is the default, so CI, the frontend and a teammate
without the weights can all run the answer path. Its answers say plainly
that they came from a mock: a fake answer that reads like a real HR one is
a fake answer somebody eventually screenshots into a report.

It can also be told to be slow, to raise, or to return something that is
not JSON — the three conditions the contracts say produce the HR fallback,
and ones the **LLM Gateway** could not be tested against otherwise.

The Gateway sits in front of whichever provider is selected and does three
things, all of them about not trusting the model:

- **The prompt carries the retrieved sections and nothing else**, so there
  is no other material to answer from.
- **The wait is bounded at 20 seconds**, which the contracts fix — so it is
  a constant in the code rather than a setting. What it stops is the
  employee waiting; it cannot stop the call itself
  ([TD-23](TECHNICAL-DEBT.md#td-23--the-20-second-timeout-stops-the-wait-not-the-call)).
- **A citation the model invented is dropped.** Every citation is matched
  against the sections that went in, and its heading comes from the
  retrieved section rather than from the model. An answer left with no
  verifiable citation is treated as a failure, because an answer nobody can
  check is the invented policy this design exists to prevent.

A timeout, a provider error and output that fails the JSON check all return
the same HR fallback message. The reason they differ goes to the log, not to
whoever asked the question.

An unrecognised `LLM_PROVIDER` is a startup error, not a quiet fall back
to the mock. A deployment that believes it is using a real model while
answering every question with "this came from the Mock LLM" would say so
nowhere anybody is looking. `real` becomes selectable with ON-18; what is
and is not true today is
[TD-01](TECHNICAL-DEBT.md#td-01--the-mock-llm-is-the-default-provider).

## Tests and lint

**Backend** (from `backend/`, with the virtual environment active):

```bash
pytest
```

```bash
ruff check .
```

Integration tests that need PostgreSQL and ChromaDB running are skipped by
default. Run them with the stack up:

```bash
pytest -m integration
```

**Frontend** (from `frontend/`):

```bash
npm test
```

```bash
npm run lint
```

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and
every pull request, in three jobs:

| Job | What it runs |
| --- | --- |
| Backend | `ruff check`, `ruff format --check`, `pytest` (unit tests) |
| Frontend | `npm run lint`, `npm test`, `npm run build`, then a check that the development token gallery is not in `dist/` |
| Integration | PostgreSQL and ChromaDB as service containers, `alembic upgrade head`, then `pytest -m integration` |

The integration job is the one worth knowing about: those tests are
deselected locally so the fast suite stays fast and Docker stays optional, so
CI is the only place they run on every change.

Everything runs on Linux while development happens on Windows, which is
deliberate — it is how a path separator or a case-sensitive import gets
caught before it reaches `main`.

Nothing is deployed. The frontend job uploads `dist/` as a run artefact; see
TD-15 in [`TECHNICAL-DEBT.md`](TECHNICAL-DEBT.md).

## Checking that the tests mean something

Every ticket ends with a fault-injection pass: a list of single edits that
each break one thing, applied to the working tree one at a time with the
relevant tests run against each.

```bash
python tools/inject/inject.py tools/inject/faults/ON-45.py
```

A fault no test notices is a test that was not testing anything, and the
exit code is non-zero if any fault went unnoticed **or could not be
applied**. The second half matters: a `before` string that matches nothing
is a fault that never ran, and "13/19 caught, 6 skipped" reads a lot like a
pass. The faults for a ticket live in `tools/inject/faults/` as data, so
the next person can re-run them.

This has earned its place. Across ON-39 to ON-45 it caught, among others, a
size limit that read the whole upload before checking it, a 20-second
timeout that waited out the provider anyway, and four tests of mine that
were passing without testing their subject.

## Watching a build

A local page shows what is happening while you work: the current test run with
its live output, the git state, which services are up, and a timeline.

```bash
python tools/watch/watch_server.py
```

Then open <http://127.0.0.1:8777>, and put `run.py` in front of commands whose
progress should appear there:

```bash
python tools/watch/run.py --label "backend pytest" --cwd backend -- pytest
```

Output still streams to your terminal and the exit code is passed through.
See [`tools/watch/README.md`](tools/watch/README.md).

## Layout

```
backend/
  app/
    api/          the four router groups from the Interface Contracts
    db/           Main Database (PostgreSQL) engine, session and tables
    services/     Auth, Document Upload, Logging, Escalation, QA Controller,
                  Retrieval, Embedding Client, LLM Gateway
      auth/       password hashing, login tokens, the seeded accounts
      documents/  File Storage, text extraction, sections
      llm/        the LLMProvider interface and the Mock LLM
    vectorstore/  Vector Database (ChromaDB) client
    config.py     settings, read from the environment
    main.py       application factory
  migrations/     Alembic: how the Main Database tables are created
  tests/
frontend/
  src/
    styles/       design tokens and base styles
    components/   the shared UI component library
    shell/        the app shell, the route table and the route guards
    session/      who is signed in, and the two roles
    dev/          the development token and component galleries
  README.md       how the interface is put together
data/
  handbook/       the synthetic company handbook, as TXT and PDF
  evaluation/     the 30-question evaluation set
scripts/          developer scripts
tools/
  watch/          the development watcher page
docs/             architecture diagram and Interface Contracts
```

## The synthetic company handbook

[`data/handbook/`](data/handbook/) holds the approved HR document set the
assistant answers from: eight documents for a fictional company, Larkfield
Systems, in both TXT and PDF. No real employee, company or customer data is
used anywhere in it.

`txt/` is the source of truth and `pdf/` is generated from it. Edit the TXT,
then regenerate:

```bash
python scripts/build_handbook_pdfs.py
```

The corpus deliberately leaves some subjects uncovered so the HR fallback path
can be tested. [`data/handbook/README.md`](data/handbook/README.md) lists both
the facts the evaluation questions rely on and the gaps, and the tests fail if
either changes.

## The evaluation question set

[`data/evaluation/questions.json`](data/evaluation/questions.json) holds the 30
questions the assistant is measured against. Twenty are answerable and carry
their expected answer and the handbook section that answers it; ten are
unanswerable and must produce the HR fallback rather than an invented policy.

The questions are checked against the handbook itself — section references,
quoted sentences and every figure in an expected answer — so a mistake in the
test data cannot be mistaken later for the assistant answering badly. See
[`data/evaluation/README.md`](data/evaluation/README.md).

## Technical debt

[`TECHNICAL-DEBT.md`](TECHNICAL-DEBT.md) records every shortcut taken during
the build, with what it costs and how it gets paid back. Add an entry in the
same pull request as the shortcut.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming, commit message and
pull request conventions. [CLAUDE.md](CLAUDE.md) holds the full working
agreement, including the board rules.
