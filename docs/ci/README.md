# CI/CD pipeline evidence (ON-49)

The pipeline is [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml).
What it runs, and why, is in the
[repository README](../../README.md#continuous-integration).

## First fully successful run

**Run 43146186371**, triggered by the pull request for ON-49 on
12 November 2026 at 03:08 UTC, on branch `ON-49-ci-pipeline`.

<https://github.com/jkwakyi/OnboardAI/actions/runs/43146186371>

| Job | Result | Duration |
| --- | --- | --- |
| Frontend | success | 15s |
| Backend | success | 41s |
| Integration | success | 1m 6s |

Every step in every job:

| Job | Step | Result |
| --- | --- | --- |
| Frontend | Install (`npm ci`) | success |
| Frontend | Lint (`npm run lint`) | success |
| Frontend | Unit tests (`npm test`) | success |
| Frontend | Build (`npm run build`) | success |
| Frontend | The development token gallery is not in the build | success |
| Frontend | Keep the built frontend (artefact upload) | success |
| Backend | Install (`pip install -e ".[dev]"`) | success |
| Backend | Lint (`ruff check .`) | success |
| Backend | Check formatting (`ruff format --check .`) | success |
| Backend | Unit tests (`pytest`) | success |
| Integration | Initialize containers (PostgreSQL 16, ChromaDB 1.5.9) | success |
| Integration | Wait for ChromaDB | success |
| Integration | Create the Main Database tables (`alembic upgrade head`) | success |
| Integration | Integration tests (`pytest -m integration`) | success |

## The run before it, which failed, and what it found

Run 43145903930 failed its Frontend job, and it was right to. jsdom 31 pulls
in `undici` 8, which declares `node >= 22.19.0`; on Node 20 every Vitest
worker dies inside `undici` before a single test runs. The repository README
had been telling contributors that Node 20 was enough.

Nobody had noticed because everyone working on this is already on a newer
Node. That is the pipeline earning its place on its first run: CI runs Linux
on a clean machine, development happens on Windows on a configured one, and
the gap between them is exactly where this kind of thing hides.

Fixed in commit `82fd66a`: CI pins Node 24, `frontend/package.json` declares
the engine so `npm` complains locally, and the README prerequisite is
corrected.

## The screenshot

**Outstanding — Jared.** The acceptance criterion asks for a screenshot of a
successful run saved for the portfolio. The repository is private, so the run
page cannot be reached without a signed-in GitHub session, and nothing in
this project's tooling has one.

To finish it: open the run URL above, screenshot the page showing the three
green jobs, and save it here as `docs/ci/successful-run.png`. The tables
above are the same information in text, so nothing is lost in the meantime —
but the portfolio asks for the image.
