# OnboardAI

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
| Embedding API | External, over HTTPS |
| LLM | Behind an `LLMProvider` interface; Mock LLM or a real provider |

The design is fixed and lives in [`docs/`](docs/). The Interface Contracts are
the source of truth for endpoints, fields and error formats.

## Prerequisites

- **Python 3.12 or 3.13** (3.14 is not yet supported by all dependencies)
- **Node.js 20 or newer**
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
uvicorn app.main:app --reload
```

The API is at <http://localhost:8000> and its generated documentation at
<http://localhost:8000/docs>. On startup the log says whether the Main
Database and Vector Database are reachable; if either is not, start the
stack with `docker compose up -d`.

### 3. Frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm install
npm run dev
```

The app is at <http://localhost:5173>.

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

## Layout

```
backend/
  app/
    api/          the four router groups from the Interface Contracts
    db/           Main Database (PostgreSQL) engine and session
    services/     Auth, Document Upload, Logging, Escalation, QA Controller,
                  Retrieval, Embedding Client, LLM Gateway
    vectorstore/  Vector Database (ChromaDB) client
    config.py     settings, read from the environment
    main.py       application factory
  tests/
frontend/
  src/            React application
docs/             architecture diagram and Interface Contracts
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming, commit message and
pull request conventions. [CLAUDE.md](CLAUDE.md) holds the full working
agreement, including the board rules.
