# CLAUDE.md — OnboardAI working agreement

This file is the standing brief for any AI agent or new contributor working in
this repository. Read it before touching code.

## Project

OnboardAI is an AI employee onboarding assistant built for CMSC 495 by
Brad Campos, Jared Ahenkora-Kwakyi and Muhammed Ayday.

Employees ask questions in a chat page and get answers with citations drawn
from HR documents that an HR administrator has approved and uploaded
(retrieval-augmented generation). When retrieval finds no good match, or the
LLM times out, errors or returns invalid JSON, the employee gets an **HR
fallback** rather than an error or an invented policy, and can escalate the
question to the HR Inbox.

**Stack:** React frontend, FastAPI backend (one application, modular
monolith), PostgreSQL (Main Database), ChromaDB (Vector Database), an
Embedding API, and an LLM behind a provider interface.

## `docs/` is the source of truth

The design is fixed. It lives in `docs/`:

- `OnboardAI-System-Architecture.png` / `.drawio` — components, data flows,
  and the numbered steps (1-9 ask, U1-U4 upload, E1-E4 escalation).
- `OnboardAI-Interface-Contracts.docx` — **the** source of truth for
  endpoints, fields and error formats.

**Do not invent endpoints, fields or error formats.** The contracts define
exactly nine endpoints. If the work needs something the contracts do not
define, stop and ask Jared rather than inventing it.

### The nine endpoints

| Endpoint | Used by |
| --- | --- |
| `POST /api/auth/login` | Login Page |
| `POST /api/documents` | Admin Upload Page (HR only) |
| `GET /api/documents` | Admin Upload Page (HR only) |
| `DELETE /api/documents/{id}` | Admin Upload Page (HR only) |
| `POST /api/chat/ask` | Chat Page |
| `POST /api/chat/feedback` | Chat Page |
| `POST /api/escalations` | Chat Page ("Send to HR") |
| `GET /api/escalations` | HR Inbox Page, Chat Page |
| `PATCH /api/escalations/{id}` | HR Inbox Page (HR only) |

Base path `/api`. HTTP/JSON. Every request carries the login token; Auth Check
validates token and role before the request reaches an endpoint. Roles are
Employee and HR administrator.

### Rules the contracts fix

- The LLM Gateway applies a **20-second timeout** and validates the JSON output.
- Below the relevance threshold, the QA Controller **skips the LLM** and
  returns `fallback: true`.
- A timeout, provider error or invalid JSON all return the HR fallback — never
  an error to the employee.
- Retrieval returns the **top 5** matching sections.
- The only method signature the design fixes is `generate(prompt)` on the
  `LLMProvider` interface, implemented by both the Real LLM Client and the
  Mock LLM.
- The API key stays on the server, in the Real LLM Client.
- Feedback is logged for manual review, never used for automatic retraining.
- Modules communicate only through interfaces. The Chat Page never talks to
  the LLM or the databases directly.

## Repository

- Remote: <https://github.com/jkwakyi/OnboardAI.git>
- Default branch: `main`
- Three people push to this repo. **Pull and rebase before starting each
  ticket.** Never force-push and never rewrite history.

## Jira

- Board: <https://jkwakyi.atlassian.net/jira/software/projects/ON>
- Site `jkwakyi.atlassian.net`, project key `ON`,
  cloudId `31b2816c-e247-40b8-94d7-8abc60e98d1a`
- Use the Atlassian MCP server for all reads and updates.
- Transition ids: Backlog `11`, To Do `21`, In Progress `31`, Done `41`
  (confirm with `getTransitionsForJiraIssue`).
- **Do not change assignees, dates, priorities or links.**

## Board rules

1. **Backlog** holds only blocked tickets (an unresolved "is blocked by"
   link). Anything workable is in **To Do**, anything being worked is
   **In Progress**, finished is **Done**.
2. Work only on **To Do** tickets. Pick by priority (Highest first), then
   earliest due date. Before starting, read the ticket, its parent epic and
   its comments.
3. Move a ticket to In Progress when you start it. One ticket In Progress at
   a time unless two are genuinely independent.
4. A ticket is **Done** only when every acceptance criterion is met, tests are
   written and passing, CI is green on the PR (ON-49 builds the pipeline;
   until it exists, run tests locally), and the PR is merged to `main`. Then
   move it to Done and comment: what changed, the PR link, how it was tested.
5. After each Done, check every ticket it was blocking. If all of that
   ticket's blockers are Done, move it Backlog to To Do. Never leave a
   workable ticket in Backlog or a blocked ticket in To Do.
6. If blocked mid-ticket, comment on the ticket saying why and tell Jared. Do
   not invent a workaround that changes scope.
7. **Development tickets only.** Do not create administrative tickets
   (papers, reports, videos, submissions). These are administrative and are
   being removed from the board — ignore them: ON-28, ON-30, ON-31, ON-35,
   ON-50, ON-53, ON-55, ON-57, ON-58, ON-59, ON-60, ON-61.
8. **Do not create new tickets without asking Jared.** If you find missing
   work, describe it and propose a ticket.

## Git conventions

See `CONTRIBUTING.md` for the full version. In short:

- One branch per ticket, `ON-<n>-short-slug`, cut from `main`.
- Commit messages start with the ticket key: `ON-<n>: imperative summary`.
- Keep commits small and meaningful.
- One PR per ticket, titled `ON-<n>: ...`, linking the Jira ticket.
- **Never commit** secrets, API keys, `.env` files, model weights or the
  local LLM. They stay in `.gitignore`; `.env.example` documents the shape.

## Tickets that need Jared

- **ON-10 — Embedding API provider and key.** Ask Jared which provider to
  use. He puts the key in his own local `.env`. **Never ask him to paste a
  key into chat.**
- **ON-18 — real local LLM.** Ask which models he has downloaded and what
  hardware he has, agree the selection criteria with him, then select. Keep
  the Mock LLM selectable by configuration so CI and teammates without the
  model can still run the system.

## UI (epic ON-62)

Build in order: tokens (ON-63), shared components (ON-64), app shell (ON-65),
then the pages. Original design only — use the token values in ON-63, no
third-party template assets, no product branding. Pages talk to the backend
only through the API client from ON-38.

## The development watcher (standing rule)

**All development is watchable.** Jared should never have to take "no output"
on trust: there is always a live page showing what is happening.

- Start the watcher at the beginning of a working session and leave it
  running:

  ```bash
  python tools/watch/watch_server.py
  ```

  It serves <http://127.0.0.1:8777>.

- Run tests, lint and other long commands **through** it, so their progress
  and output reach the page:

  ```bash
  python tools/watch/run.py --label "backend pytest" --cwd backend -- pytest
  ```

  Output still streams to the terminal and the exit code still passes
  through, so this costs nothing.

- The page shows only live data. If something cannot be measured yet, the
  page says so rather than showing a placeholder.

- **Keep the Jira board panel fresh.** After moving a ticket, or whenever the
  board changes, write a new snapshot so Jared can see the board without
  leaving the page:

  ```bash
  python tools/watch/sync_board.py --from <jira-search-result.json>
  ```

  Pass the saved Atlassian MCP search result. The panel header shows how long
  ago it synced, so a stale board is visible rather than misleading.

`tools/watch/README.md` has the detail, including the optional live-polling
mode for when the assistant is not running.

## Technical debt (standing rule)

**Record a shortcut in the same pull request that takes it.** Add an entry to
[`TECHNICAL-DEBT.md`](TECHNICAL-DEBT.md) stating what was done, why, the
impact and the mitigation.

A log written at the end is a log written from memory, and the entries that
get forgotten are exactly the ones nobody wanted to admit to. ON-51 keeps it;
it is the source for the Refinement Report.

Hardcoded values, mock implementations, skipped tests, deferred decisions and
"we will fix this after the alpha" all count.

## Quality

- Write tests with each ticket and run lint.
- Remove placeholder data once the real endpoint exists.
- Keep the README current with install and run steps.
- Write cross-platform code and scripts: development happens on Windows,
  CI runs Linux.

## Dates

- Alpha release: **Tuesday 17 November 2026, 11:59 pm ET**.
