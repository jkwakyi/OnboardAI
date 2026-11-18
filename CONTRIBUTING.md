# Contributing

Three of us push to this repo: Brad, Jared and Muhammed. These are the rules
we work to, so our history stays readable and we can review each other's
work without guessing.

## Starting a ticket

Take the top ticket from **To Do** on the
[ON board](https://jkwakyi.atlassian.net/jira/software/projects/ON) — highest
priority, then earliest due date. Read it and its comments, move it to **In
Progress**, and assign it to yourself.

Update main before you branch:

```bash
git checkout main && git pull --rebase origin main
```

## Branches and commits

One branch per ticket, cut from main, named after the ticket:

```bash
git checkout -b ON-11-main-database-schema
```

Every commit starts with the ticket key and an imperative summary:

```
ON-11: add users and documents tables to the Main Database schema
```

Not `fix`, not `updates`, not `WIP`. Keep commits small — one logical change
each. If the reason isn't obvious from the diff, add a body after a blank
line explaining why, not what.

## Pull requests

One per ticket, titled `ON-<number>: what this delivers`. In the description
say what changed and why, link the Jira ticket, and say how you tested it.

Before you open it, rebase on main and make sure both sides pass:

```bash
cd backend && pytest && ruff check .
```

```bash
cd frontend && npm test && npm run lint
```

Ask a teammate for review. Once CI is green and it's merged, move the ticket
to **Done** and comment with what changed, the PR link, and how you tested.

## Don't force-push

Not on main, not on a shared branch. Someone else may have pulled it. If you
need to undo something, commit the undo.

## Don't commit secrets

API keys, `.env` files, model weights — none of it goes in. `.gitignore`
covers them. If you add a setting, put it in `.env.example` with a blank or
a safe default, never a real value.

## Style

Python is `ruff` (`ruff check .` and `ruff format .` from `backend/`).
TypeScript is `oxlint` (`npm run lint` from `frontend/`). Write tests with
the ticket — it isn't done without them.

## The contracts are fixed

`docs/OnboardAI-Interface-Contracts.docx` defines our nine endpoints, their
fields and their error formats. Don't invent endpoints or fields. If you need
something it doesn't cover, raise it with the team first.
