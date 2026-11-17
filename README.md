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
| LLM | Behind an `LLMProvider` interface; `qwen3:8b` on local Ollama, or the Mock LLM |

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

A valid key on an account with no credit answers **429
`insufficient_quota`**, not 401 — so "the key is wrong" and "the account is
empty" look nothing alike, and the script says which it was.

#### Running without a key

Uploading a document needs the Embedding API, because the upload embeds
its sections before it answers. If you have no key — CI does not, and
neither does a teammate's checkout — set:

```
EMBEDDING_PROVIDER=mock
```

That embeds locally with no account and no network, using the hashing
trick: every word is hashed into a bucket, so texts that share words land
near each other. It is enough to run the whole system and to exercise
retrieval, the top-5 cut and the relevance threshold.

It is **lexical, not semantic**: "annual leave" and "paid time off" mean
the same thing and share no words, so the mock treats them as unrelated.
Anything that judges whether the *right* section was found has to run
against the real provider. It logs a warning every time it is selected, and
it is never a fall back — an unrecognised `EMBEDDING_PROVIDER` is an error.
See [TD-27](TECHNICAL-DEBT.md#td-27--the-mock-embedder-is-lexical-not-semantic).

Do not query a collection with one provider after building it with the
other. The vector widths differ, so ChromaDB refuses the mismatch rather
than returning nonsense — but delete the collection when switching rather
than relying on that.

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

### Signing in from the interface

Start the backend and the frontend, open the app, and sign in with one of
the seeded accounts above. There are no development shortcut buttons any
more — ON-65 shipped two and ON-38 deleted them, because a password-free way
in that only works in development is still one somebody eventually ships.

The token is kept in `sessionStorage`, so a refresh keeps you signed in and
closing the tab signs you out. What that costs is
[TD-24](TECHNICAL-DEBT.md#td-24--the-login-token-is-readable-by-script-on-the-page):
script on the page can read it, which is the trade against an `httpOnly`
cookie and the CSRF work that comes with one.

There is one piece of session state, the token, and the name and role shown
in the interface are read out of its claims. Those claims are **not
verified** — a browser cannot check a signature — so they decide which
navigation to draw and nothing more. Auth Check enforces the role on every
request, which means editing the token in devtools changes the rail and
changes nothing the server will honour.

`frontend/.env.example` has `VITE_API_BASE_URL` if the backend is not on
`localhost:8000`. Nothing secret may go in that file: Vite bakes every
`VITE_`-prefixed variable into the bundle it ships to the browser.

### Uploading a document

From the interface, sign in as the HR administrator and open **Documents**.
Drop a PDF or TXT on the dropzone, or click to browse, and press Upload.
The ring counts the bytes going out; when they are all up it changes to
"Reading …", because the server extracts the text and splits it into
sections before it answers, and a bar sitting at 100% while that happens
reads as a hung page.

A success now means all four upload steps finished: **the file is stored,
its text has been read and split into sections, and those sections can be
found when an employee asks a question**. Since ON-41 the request also
embeds every section and writes the vectors to the Vector Database before
it answers, so a 201 is a promise the whole pipeline ran. If the Embedding
API or ChromaDB cannot be reached, the upload is refused with a 500 and
discarded entirely — no row, no file, no sections, no stray vectors —
rather than storing a document the assistant could never cite.

That is also why uploading needs `EMBEDDING_API_KEY` set, or
`EMBEDDING_PROVIDER=mock` — see [Running without a key](#running-without-a-key).

A file the browser can already tell is wrong — not a PDF or TXT, or empty —
is refused without a request being made. A file the server refuses shows
the server's own wording, and a **Try again** button appears only when
trying again could work: a 500, a 429 or an unreachable server get one, a
413, 415, 422 or 400 do not, because those are properties of the file and
it will be refused identically next time.

There is no list of uploaded documents and no way to delete one, because
`GET /api/documents` and `DELETE /api/documents/{id}` are ON-16 and do not
exist on the server yet — see
[TD-25](TECHNICAL-DEBT.md#td-25--the-admin-upload-page-uses-one-of-its-three-endpoints).
An upload in progress cannot be cancelled either:
[TD-26](TECHNICAL-DEBT.md#td-26--an-upload-cannot-be-cancelled).

Or with `curl`:

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

### Asking a question from the interface

Sign in as either role and open **Chat**. Type a question, press Enter
(Shift+Enter for a new line) and the turn appears in the transcript while
it waits — the LLM Gateway allows the model twenty seconds, so the wait is
part of the page rather than a spinner on a button.

An answer shows the text and, under **Drawn from**, a chip per section it
used: the document and the heading, taken from the retrieved section
rather than from the model, so a citation cannot be mislabelled even when
its id is right. The chips are not pressable — opening a section needs an
endpoint that reads one, and the contracts define no such endpoint.

**A fallback is drawn as a normal turn, not as an error.** It gets a
quiet "No answer found" pill and the message directing the employee to
HR. That is deliberate and it is the page's most important behaviour: the
assistant declining to invent a policy is it working, and an employee
shown that in red learns the opposite. Red is kept for the things that
really failed — the network, a refused question, a server that broke —
and those get an alert and, where trying again could work, a retry.

**The transcript is this visit only.** Every chat is saved server-side
(ON-47), but none of the nine endpoints reads chat history back, so a
reload starts an empty page. Nothing on the page pretends otherwise.

### Sending a question to HR

A fallback is the end of what the assistant can do, so it carries a
**Send to HR** button (E1). Pressing it saves the question as an open
escalation (E2); once it is saved the button is replaced — not disabled
— by a line saying HR has the question and will reply here. A disabled
button says "you cannot do this"; what is true is "this is done".

`POST /api/escalations` takes **one field**, `chat_log_id`, and nothing
else:

```json
{ "chat_log_id": 13 }
```

The question is not sent. The server reads what was asked out of that
chat log, which is the only way the question in HR's inbox is the
question the employee actually asked — otherwise any caller could put
any words in front of an HR administrator, attached to a chat log that
says something else. The endpoint also refuses an answer that is not the
caller's (`404`, worded identically to one that does not exist, so the
two cannot be told apart) and one that was answered rather than fallen
back on (`409`). The button only appears on a fallback, but a button
that is absent is not a rule.

Pressing it twice is safe: the open escalation that already exists comes
back rather than a second one. What that does and does not guarantee is
[TD-35](TECHNICAL-DEBT.md#td-35--one-escalation-per-question-is-a-convention-not-a-constraint).

HR replying and the employee seeing the reply (E3, E4) are ON-21 and
ON-22, so for now an escalation goes into the table and waits.

### Finding the sections that answer a question

The Retrieval Service (`backend/app/services/retrieval/`) does steps 5 and
6: the question is embedded by the same client and the same model that
embedded the documents, the Vector Database is asked for the five closest
sections, and the text comes back out of the Main Database.

Two lookups, not one, because the Vector Database holds vectors and ids
and deliberately not the text — PostgreSQL keeps the one approved copy of
every section, so there is nothing for the two stores to disagree about.
That makes the join this component's real work: `WHERE id IN (...)` returns
rows in whatever order the planner likes, so the rows are put back into the
order ChromaDB ranked them before anything sees them. A ranking lost here
produces no error at all — five genuinely close sections, ordered by
accident, and a confident answer built out of them.

Each result carries a **score**: `1.0` for a section pointing exactly where
the question does, falling as the angle opens, and below zero for one
pointing the other way. It is not clamped, because "useless" and "actively
wrong" are different things and ON-46's relevance threshold is the thing
that needs to tell them apart. Retrieval itself applies no threshold and
decides nothing: it returns what it found, with the number to judge it by.

**The collection has to be in cosine space.** That score is `1 - distance`,
which is true for cosine and false for ChromaDB's default of `l2`. The two
rank unit vectors identically, so a collection in the wrong space returns
the right five sections with wrong scores and nothing to show for it. The
collection is therefore created as cosine and **checked** on every use —
asking is not the same as getting, because `get_or_create_collection`
silently ignores the metadata for a collection that already exists. A
collection made before ON-43 is refused with a message naming it and the
command to delete it; delete it and re-upload the documents. Why there is
no automatic migration is
[TD-29](TECHNICAL-DEBT.md#td-29--an-existing-chromadb-collection-cannot-be-moved-to-cosine).

### Asking a question

`POST /api/chat/ask` is the whole ask flow, steps 1 to 9. The question
goes in, the answer with its citations comes out, and the chat is saved
before the response is sent.

```json
{ "question": "How many days of paid time off do I accrue in my fourth year?" }
```

```json
{
  "id": 5,
  "answer": "...",
  "citations": [
    { "section_id": 475, "heading": "4.1 PAID TIME OFF", "document": "04-time-off-and-leave.txt" }
  ],
  "fallback": false
}
```

`id` is the saved chat log. The Chat Page needs it to rate an answer and
to click "Send to HR" on a fallback so HR's reply comes back against the
right message (E4), so it is always a row that exists — which is why a
database failure here is a `500` rather than a fallback carrying an id
that points at nothing.

**The AI path never produces an error status.** No good match, nothing
retrieved, the Embedding API down, the model timing out, output that
fails the JSON check: all of them are `200` with `fallback: true` and the
same message directing the employee to HR. What is still an error is a
question that is blank or longer than the Gateway will read (`422`), a
token that is missing or invalid (`401`), and the Main Database refusing
to record the chat (`500`).

The heading and document on a citation come from the retrieved section
rather than from the model, so a citation cannot be mislabelled even when
its id is right.

### When the assistant declines to answer

The QA Controller (`backend/app/services/qa/`) runs the ask flow and makes
the one decision the contracts give it: **if the best retrieved section
scores below the relevance threshold, the LLM is not asked at all.**

Not asked, rather than asked and overruled. A model handed five
irrelevant sections and a direct question will usually answer it anyway,
from what it learnt in training rather than from an approved HR document,
and that answer reads exactly like a good one. Skipping the call is the
only thing standing in its way, so the test that matters is not that a
fallback came back — it is that the provider was never called. The live
check counts those calls and requires zero.

Whatever way the AI path declines — below the threshold, nothing
retrieved, the Embedding API down, the model timing out, output that
fails the JSON check — the employee sees the same message directing them
to HR. The reason is recorded for the log and never rendered: the
difference between "the model timed out" and "the handbook does not cover
this" is not something an employee can act on, and either way the next
step is to ask HR.

**The threshold is provisional, and the number is measured.**
`RELEVANCE_THRESHOLD` ships at 0.22 — the value that best separated the
[evaluation question set](#the-evaluation-question-set)'s twenty
answerable questions from its ten unanswerable ones, swept over the real
stack.

It was measured against the **mock embedder**, because the Embedding API
account has no credit, and the two score distributions overlap: the best
unanswerable question outscores the median answerable one, so no
threshold separates them cleanly. At 0.22 it refuses none of the twenty
answerable questions and lets six of the ten unanswerable ones through.
What catches the rest is the LLM Gateway dropping an answer that cites
nothing it was given — a second defence that does not engage under the
Mock LLM, which cites whatever it is handed. All of this is
[TD-30](TECHNICAL-DEBT.md#td-30--the-relevance-threshold-is-tuned-against-the-wrong-embedding-model),
and tuning it properly belongs to the evaluation story.

**What that looks like from the outside.** Asked over HTTP against the
whole handbook, with the mock embedder:

| Question | Answered? |
| --- | --- |
| How many days of paid time off do I accrue in my fourth year? | yes |
| How much holiday do I get? | no — fallback |
| What is my annual leave entitlement? | no — fallback |
| What is the airspeed velocity of an unladen swallow? | **yes** |

The handbook says "paid time off". The mock matches words rather than
meaning, so the two real questions that avoid its vocabulary are refused,
and the nonsense one — which is mostly ordinary English words that appear
throughout the handbook — scores 0.333 and sails past a threshold tuned
on real questions. **Judge nothing about answer quality from a run on the
mock.** It exists so the system can be run without a key, not so it can
be assessed.

### Which language model answers

Out of the box, nothing downloads a model and nothing needs a key:

```
LLM_PROVIDER=mock
```

The design puts an `LLMProvider` interface in front of the model, with the
one method the contracts fix — `generate(prompt)`. The **Mock LLM**
implements it and is the default, so CI, the frontend and a teammate
without the weights can all run the answer path. Its answers say plainly
that they came from a mock: a fake answer that reads like a real HR one is
a fake answer somebody eventually screenshots into a report.

#### Real answers, from a model on your own machine

The **Real LLM Client** implements the same interface and talks to
[Ollama](https://ollama.com) over the loopback address. There is no key
and nothing leaves the machine — the handbook text in the prompt goes no
further than your own GPU.

```bash
ollama pull qwen3:8b
```

```
LLM_PROVIDER=real
LLM_MODEL=qwen3:8b
LLM_API_URL=http://127.0.0.1:11434/api/generate
```

`qwen3:8b` was chosen by running the candidates against the prompts the
Gateway actually builds, over the real handbook:

| Model | Answered | Slowest | Why |
| --- | --- | --- | --- |
| **qwen3:8b** | **5 of 5** | **4.3 s** | Selected. |
| `mistral:7b` | 4 of 5 | 3.8 s | Cited section 1 while naming 650 in its prose. |
| `llama3.2:latest` | 1 of 5 | 1.6 s | Cites the handbook's own numbering (`4.1`) rather than the section id it was given, so the Gateway drops every citation. |

`deepseek-r1:14b` was not a candidate: its thinking traces fight the JSON
check.

**Reasoning is turned off** in the request, and that is the difference
between working and not. The same question took 18.6 seconds with qwen3
thinking and 4.0 without — identical answer, identical citation, 380
output tokens against 87. The Gateway allows 20, so thinking on spends
most of the budget generating text the JSON check discards.

End to end through `POST /api/chat/ask`, with the model loaded: eight
questions, slowest **8.2 s**, median **4.9 s**. The two unanswerable ones
came back in 0.3 and 1.7 seconds, because below the relevance threshold
the QA Controller never asks the model at all.

A model that has been unloaded takes about a minute to load, which is past
the Gateway's limit — so the first question after a long pause gets the HR
fallback and the next one works. `LLM_KEEP_ALIVE` holds it for 30 minutes;
the rest is
[TD-36](TECHNICAL-DEBT.md#td-36--a-cold-model-load-outlasts-the-gateways-timeout).

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
to the mock, and selecting the mock logs a warning every time. A
deployment that believes it is using a real model while answering every
question with "this came from the Mock LLM" would say so nowhere anybody
is looking. The mock stays the default because CI has no GPU; see
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

A frontend faults file adds `RUNNER = "vitest"` and `ROOT = "frontend"`;
the harness runs whatever `TESTS` names and a non-zero exit is a non-zero
exit either way. `TESTS` may be one path or a list of them, for a component
whose tests do not fit in a single file.

This has earned its place. Across ON-39 to ON-42 it caught, among others, a
size limit that read the whole upload before checking it, a 20-second
timeout that waited out the provider anyway, and ten tests of mine that
were passing without testing their subject — including three that spied on
`window.sessionStorage`, which in jsdom is a Proxy, so the spy attached and
intercepted nothing while the tests went green either way.

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
      embedding/  the Embedding Client, the hosted API and the mock
      llm/        the LLMProvider interface, the Mock LLM and the real client
      retrieval/  the Retrieval Service: question in, top 5 sections out
      qa/         the QA Controller: the relevance threshold and the fallback
      logs/       the Logging Service: saved chats
      escalations/ the Escalation Service: a fallback question sent to HR
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
