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

All styling comes from the design tokens in
`frontend/src/styles/tokens.css` — no component contains a colour. The groups,
the measured contrast ratios and the development token gallery at
<http://localhost:5173/#tokens> are documented in
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
    vectorstore/  Vector Database (ChromaDB) client
    config.py     settings, read from the environment
    main.py       application factory
  migrations/     Alembic: how the Main Database tables are created
  tests/
frontend/
  src/
    styles/       design tokens and base styles
    dev/          the development token gallery
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
