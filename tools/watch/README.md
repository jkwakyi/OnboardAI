# The development watcher

A local page showing what is actually happening while OnboardAI is being
built: the current test run with its live output, the git state of the
checkout, whether each service is reachable, and a timeline of what has run.

It is a development tool. It is not part of the product, it is never deployed,
and it only ever reads the repository.

## Start it

From the repository root, with the backend virtual environment active:

```bash
python tools/watch/watch_server.py
```

Then open <http://127.0.0.1:8777>. The page polls once a second and needs no
build step.

If something else is already on the port, the server says so and stops rather
than starting shadowed behind it. Pick another:

```bash
python tools/watch/watch_server.py --port 8778
```

Leave it running; it survives everything else being restarted.

## Run things through it

Put `run.py` in front of any command whose progress should appear on the page:

```bash
python tools/watch/run.py --label "backend pytest" --cwd backend -- pytest
```

```bash
python tools/watch/run.py --label "frontend tests" --cwd frontend -- npm test
```

```bash
python tools/watch/run.py --label "backend lint" --cwd backend -- ruff check .
```

Output still streams to your terminal exactly as it would otherwise, and the
exit code is passed through, so nothing is hidden or swallowed by running a
command this way.

Progress is parsed from the output as it arrives: pytest's running percentage
and summary line, and vitest's test counts. A command the parser does not
recognise still shows its state, elapsed time and full output — it just has no
progress percentage.

## What the page shows

| Panel | Where it comes from |
| --- | --- |
| State, progress, time, counts | the running command, parsed live |
| Progress over time | one point per change in percentage |
| Output | the tail of the current run, following unless you scroll up |
| Jira board | a snapshot in `.watch/board.json` — see below |
| Ticket | the `ON-<n>` in the branch name, linked to Jira |
| Git | branch, head commit, position against the remote, uncommitted files |
| Services | a TCP connect to PostgreSQL, ChromaDB, the backend and the frontend |
| Timeline | every run that has started and finished |
| Recent commits | `git log` |

Everything on the page is read live. Nothing is placeholder or mock data: if a
panel has nothing to show, it says so.

## The Jira board, without leaving the page

The board panel shows the four column counts, how far through the development
tickets the project is, what is In Progress, the next few To Do tickets by
priority, and what was finished recently. Ticket keys link to Jira, and the
ticket matching the current branch is highlighted.

It gets its data one of two ways, and the panel header says which.

### Agent-synced — the default, no setup

The assistant already reads Jira through the Atlassian MCP server while it
works, so it writes what it sees to `.watch/board.json`:

```bash
python tools/watch/sync_board.py --from <search-result.json>
```

The input can be a saved MCP tool result or a raw Jira REST response; both
shapes are accepted.

This means the board on the page is **the board the assistant is working
from**, and it changes the moment a ticket moves rather than on a polling
interval. It needs no credential, and it cannot drift from what the assistant
believes, because it is the same data.

The cost is that it only updates while the assistant is working. The header
says how long ago it synced, so a stale board is obvious rather than
misleading.

### Live — opt-in

To have the watcher poll Jira itself every 60 seconds, set `JIRA_EMAIL` and
`JIRA_API_TOKEN` in `.env`. Create a token at
<https://id.atlassian.com/manage-profile/security/api-tokens>. `.env` is
gitignored; the token never leaves your machine.

The server says which mode it started in. Both write the same file, so the
page does not care which one is in use.

Administrative tickets and epics are left out of the counts, matching the
board rules in `CLAUDE.md`.

## How it fits together

Two pieces that talk through files in `.watch/`, so either can be restarted
without disturbing the other:

```
run.py            runs a command, parses progress, writes .watch/state.json
                  and .watch/output.log
watch_server.py   reads those, adds git and service state, serves the page
index.html        the page; plain HTML and JavaScript, no build, no dependencies
```

`.watch/` is runtime state and is ignored by Git.

The server binds to `127.0.0.1` only, so the page is not reachable from
anywhere else on the network.
