# Contributing to OnboardAI

Three people push to this repository: Brad Campos, Jared Ahenkora-Kwakyi and
Muhammed Ayday. These conventions keep the history readable and let us review
each other's work.

## Before you start a ticket

1. Pick a ticket from **To Do** on the
   [ON board](https://jkwakyi.atlassian.net/jira/software/projects/ON),
   highest priority first, then earliest due date.
2. Read the ticket, its parent epic and its comments.
3. Move it to **In Progress** and assign it to yourself.
4. Update your local `main` first:

```bash
git checkout main && git pull --rebase origin main
```

## Branches

One branch per ticket, cut from `main`, named for the ticket:

```
ON-<number>-short-slug
```

For example `ON-9-scaffold-backend-frontend`, `ON-11-main-database-schema`.

```bash
git checkout -b ON-11-main-database-schema
```

## Commit messages

Every commit starts with its ticket key, then an imperative summary:

```
ON-<number>: imperative summary
```

Good:

```
ON-11: add users and documents tables to the Main Database schema
ON-44: add Mock LLM implementing the LLMProvider interface
```

Not useful:

```
fix
updates
WIP
```

Keep commits small and meaningful — one logical change each. A reviewer
should be able to read the subject line and know what changed. Add a body
after a blank line when the *why* is not obvious from the diff:

```
ON-17: return the HR fallback when retrieval scores below threshold

The contracts require that employees never see an invented policy, so a
weak match skips the LLM entirely rather than prompting it with poor
context.
```

Wrap the subject at about 72 characters and do not end it with a full stop.

## Pull requests

One pull request per ticket, titled with the ticket key:

```
ON-<number>: what this delivers
```

The description should cover:

- **What changed** and why.
- **The Jira ticket**, linked:
  `https://jkwakyi.atlassian.net/browse/ON-<number>`
- **How it was tested** — the commands you ran and what passed.
- Anything a reviewer should look at closely.

Before opening it:

```bash
git pull --rebase origin main
```

and make sure tests and lint pass on both sides you touched:

```bash
cd backend && pytest && ruff check .
```

```bash
cd frontend && npm test && npm run lint
```

Request review from a teammate. Once CI is green and the pull request is
merged to `main`, move the ticket to **Done** and comment on it with what
changed, the pull request link, and how it was tested.

## Never force-push

Do not force-push and do not rewrite history on `main` or on a shared
branch. Others may have pulled it. If you need to undo something, add a
commit that undoes it.

## Never commit secrets

Secrets, API keys, `.env` files, model weights and local LLM files stay out
of the repository. `.gitignore` covers them and `.env.example` documents
which variables exist without their values.

If you add a new setting, add it to `.env.example` with a placeholder or a
safe local default, never a real value.

## Code style

- **Python**: `ruff` enforces the style. Run `ruff check .` and
  `ruff format .` from `backend/`.
- **TypeScript/React**: `oxlint` enforces the style. Run `npm run lint`
  from `frontend/`.
- Write tests with each ticket. A ticket is not done without them.

## The contracts are fixed

`docs/OnboardAI-Interface-Contracts.docx` defines the nine endpoints, their
fields and the error formats. Do not invent endpoints or fields. If you need
something the contracts do not define, raise it with the team rather than
adding it.
