# OnboardAI

**An AI assistant that answers new employees' HR questions from your company's own documents — and admits when it doesn't know.**

Starting a job means asking a hundred small questions. How much holiday do I
get? When do I get paid? Who do I tell if I lose my laptop? The answers are
all in the handbook, but nobody reads a handbook cover to cover, and asking
HR the same question for the fiftieth time is nobody's idea of a good week.

OnboardAI puts a chat box in front of that handbook. An employee asks a
question in plain English and gets an answer back, with a link to the exact
section it came from, so they can check it themselves.

The important part is what it does when it *can't* help. Most chatbots guess.
This one doesn't. If the handbook has nothing relevant, OnboardAI says so,
and offers to send the question to a real person in HR instead. An invented
answer about parental leave is worse than no answer at all, so the system is
built so it can't give one: every answer has to cite a section it was
actually shown, and anything else becomes a fallback.

## What you can do with it

**As an employee** you ask questions and get answers with sources. If there's
no good answer, you press one button and it goes to HR.

**As an HR administrator** you upload the documents the assistant is allowed
to use — PDFs or text files. Nothing else is ever used. If it isn't in a
document you approved, the assistant won't say it.

## The team

Built for CMSC 495.

| Name | Role |
| --- | --- |
| Brad Campos | Lead Architect |
| Jared Ahenkora-Kwakyi | Interface Designer |
| Muhammed Ayday | Integration Lead |

## How it's built

| Piece | Technology | What it does |
| --- | --- | --- |
| Frontend | React + TypeScript (Vite) | The pages people actually use |
| Backend API | FastAPI — one application, modular monolith | Every request goes through here |
| Main Database | PostgreSQL | Users, documents, sections, chat logs, feedback, escalations |
| Vector Database | ChromaDB | The numeric fingerprints that make searching by meaning possible |
| Embedding API | OpenAI `text-embedding-3-small`, over HTTPS | Turns text into those fingerprints — this is the part that costs money |
| LLM | `qwen3:8b` on local Ollama, or the Mock LLM | Writes the answer in English, behind a swappable interface |

The frontend never talks to the databases or the model directly — it only
calls the API. The design is fixed and lives in [`docs/`](docs/), where the
Interface Contracts are the source of truth for every endpoint, field and
error format.

---

# Getting it running

## What you need installed

- **[Python 3.12 or 3.13](https://www.python.org/downloads/)** — 3.14 isn't supported by all the dependencies yet
- **[Node.js 22.19 or newer](https://nodejs.org/)** — the test runner won't load on 20
- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** — runs PostgreSQL and ChromaDB for you

Then open a terminal and clone the project:

```bash
git clone https://github.com/jkwakyi/OnboardAI.git
cd OnboardAI
```

Make your own settings file from the example. **Windows:**

```bash
copy .env.example .env
```

**Mac:**

```bash
cp .env.example .env
```

Open `.env` in a text editor. Find these two lines, which are blank, and
fill them in exactly like this:

```
SEED_EMPLOYEE_PASSWORD=onboardai-employee
SEED_HR_PASSWORD=onboardai-hr
```

These are the two demo accounts you'll sign in with. They're throwaway
logins for a demo application that runs only on your own computer — they
guard nothing real, so everyone on the team uses the same ones.

They're blank in the file you copied because that file *is* in the
repository, and a real password committed to a repository is a password
everybody has forever. Your `.env` is ignored by Git and never leaves your
machine.

## Step 1 — Start the databases

Make sure Docker Desktop is running, then:

```bash
docker compose up -d
```

That starts PostgreSQL and ChromaDB in the background. You only need to do
this once per restart of your computer. To stop them later: `docker compose down`.

## Step 2 — Set up the backend

**Windows:**

```bash
cd backend; python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -e ".[dev]"
```

**Mac:**

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
```

That makes a private Python environment for the project and installs what it
needs. It takes a minute or two the first time.

## Step 3 — Create the database tables and your accounts

Still in the `backend` folder with the environment active:

```bash
alembic upgrade head
```

Then, from the main project folder:

```bash
python scripts/seed_accounts.py
```

That creates the two demo accounts. **These are your sign-in details:**

| Who | Email | Password | Role |
| --- | --- | --- | --- |
| Alex Rivera | `employee@onboardai.example` | `onboardai-employee` | Employee |
| Jordan Blake | `hr@onboardai.example` | `onboardai-hr` | HR administrator |

Both addresses end in `.example`, a domain reserved by the standards body
precisely so test accounts can never reach a real mailbox.

Run that script again any time to reset the accounts — handy if you forget
a password or wipe the database.

## Step 4 — Start the backend

From the `backend` folder:

```bash
uvicorn app.main:app --reload
```

Leave that terminal running.

## Step 5 — Start the frontend

Open a **second terminal**, go to the project folder, and:

```bash
cd frontend; npm install; npm run dev
```

Leave that one running too.

## Step 6 — Open it

Go to **<http://localhost:5173>** and sign in:

- **HR administrator** — `hr@onboardai.example` / `onboardai-hr`
- **Employee** — `employee@onboardai.example` / `onboardai-employee`

Sign in as Jordan Blake (HR) and you'll see a Documents page — upload the
sample handbook from `data/handbook/pdf/` to give the assistant something to
work with. Then sign in as Alex Rivera (Employee) and start asking questions.

### Starting it again next time

Once it's set up, you only need three things:

```bash
docker compose up -d
```

```bash
cd backend; .venv\Scripts\Activate.ps1; uvicorn app.main:app --reload
```

```bash
cd frontend; npm run dev
```

(On Mac, `source .venv/bin/activate` instead of the Windows activate line.)

---

# Using it

## Uploading documents — as HR

Sign in as **Jordan Blake**. The assistant starts out knowing nothing, so
this is the first thing to do.

Go to **Documents** and either drag a file onto the box or click it to
browse. PDFs and plain text files are accepted; anything else is refused
rather than quietly stored. Press **Upload**.

The file is read on the way in — the server pulls out the text, splits it
into sections by its headings, and indexes each one so it can be searched
by meaning later. That takes a second or two per document. If a file has no
readable text in it (a scanned page, say), it's rejected then and there
rather than sitting in the system answering nothing.

To get started, upload the sample handbook from `data/handbook/pdf/` — all
eight chapters.

> The page doesn't yet list what you've already uploaded, or let you delete
> anything. That's still being built.

## Asking a question — as an employee

Sign in as **Alex Rivera** and go to **Chat**. Type a question the way
you'd ask a person — "how much paid time off do I get?" — and press Enter.
Shift+Enter gives you a new line instead of sending.

The answer appears above the box, with one or more chips underneath it
showing exactly which document and section it came from. That's the point:
you never have to take the answer on trust, you can go and read the
paragraph it was built from.

Good questions to try against the sample handbook: *how much paid time off
do I get?*, *how do I report a security incident?*, *when do I get paid?*,
*what happens during my first week?*

## When it can't answer

Ask something the handbook doesn't cover and you'll get a **No answer
found** label instead, with a short message pointing you at HR.

This is deliberate and it's the most important behaviour in the system.
Rather than guessing, it tells you it doesn't know. Underneath is a **Send
to HR** button — press it and the question goes to a real person. The
button is replaced by a confirmation, because "you can't do this again"
and "this is done" are different things and should look different.

> HR can't read those escalations in the app yet — they're stored, waiting
> on the HR Inbox page, which is still being built.

---

# About the API key

This is the one part that costs money, so it's worth understanding before you
start.

## Why it needs one

To find the right section of a handbook, the system has to understand what a
question *means* — not just match words. "Annual leave" and "paid time off"
are the same thing and share no words at all. That understanding comes from
an outside service called an embedding API, and that service charges.

## What it actually costs

Almost nothing. Genuinely.

| What | Cost |
| --- | --- |
| Processing the entire sample handbook | **$0.00016** — about one sixtieth of a cent |
| Asking one question | **$0.0000004** |
| 25,000 questions | **1 cent** |

The catch is that OpenAI's minimum top-up is **$5**, and that $5 will outlive
this project several times over. You are not going to run out.

## How to get your own key

1. Go to <https://platform.openai.com/signup> and make an account.
2. Go to **Billing** → <https://platform.openai.com/settings/organization/billing> and add **$5**. You must do this *before* making a key — a key on an account with no money returns an error, not an answer.
3. Go to **API keys** → <https://platform.openai.com/api-keys> and click **Create new secret key**.
4. Copy it. OpenAI shows it **once** and never again.
5. Open your `.env` file and paste it after `EMBEDDING_API_KEY=`, like this:
   ```
   EMBEDDING_API_KEY=sk-your-key-goes-here
   ```
6. Check it works:
   ```bash
   python scripts/check_embedding_api.py
   ```
   It should say `1536 dimensions`. If it mentions quota or credit, go back to step 2.

Your key stays in `.env` on your own machine. That file is ignored by Git and
can't be committed by accident. Never paste a key into chat, a document, or a
screenshot — treat it like a password, because that's what it is.

## If you don't want to pay

You don't have to. Open `.env` and change this line:

```
EMBEDDING_PROVIDER=mock
```

Everything still runs — you can log in, upload documents, ask questions, use
every page. But **the answers will be visibly wrong**, and you should know how
before you judge the project by them:

- It matches words instead of meaning. Ask about "annual leave" and it may
  return the welcome page, because the handbook calls it "paid time off".
- It will answer questions it should refuse. Ask it the capital of Mongolia
  and it may confidently cite the payroll chapter.

That's the stand-in, not the system. It exists so the project can be run and
tested without a card — not so it can be demonstrated. **Use a real key for
anything you're showing to another person.**

## The answers themselves

Separately from the key, there's the part that writes the answer in English.
By default that's a stand-in too, and it's honest about it — answers begin
"This answer came from the Mock LLM" so nobody mistakes one for real.

For real answers you need [Ollama](https://ollama.com) and a model, which is
free but wants a reasonable graphics card:

```bash
ollama pull qwen3:8b
```

Then in `.env`:

```
LLM_PROVIDER=real
```

The model runs entirely on your own machine — no key, no cost, and the
handbook text never leaves your computer. The first question after a long
pause takes about a minute while the model loads, and gets the HR fallback;
ask again and it'll be a few seconds.

---

# For developers

**Tests.** From `backend/`: `pytest`. From `frontend/`: `npm test`. Linting is
`ruff check .` and `npm run lint`. GitHub Actions runs all of it on every
pull request.

**Where things are.**

```
backend/app/
  api/          the nine endpoints
  services/     auth, documents, embedding, retrieval, qa, llm, logs, escalations
  db/           database models and session
  vectorstore/  ChromaDB client
frontend/src/
  shell/        the pages and routing
  components/   shared UI components
  styles/       design tokens
data/handbook/  the sample company handbook
docs/           architecture diagram and interface contracts
```

**Known limitations.** [TECHNICAL-DEBT.md](TECHNICAL-DEBT.md) lists every
shortcut taken to reach the alpha — what it is, why it was taken, what it
costs and how it gets fixed. Thirty-seven entries.

**Contributing.** See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming,
commit messages and pull request conventions.
