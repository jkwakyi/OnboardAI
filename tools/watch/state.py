"""Shared state for the development watcher.

The watcher is two pieces that talk through files in .watch/ rather than
through a socket, so either one can be restarted without disturbing the other:

    run.py          executes a command and writes what it sees
    watch_server.py reads that and serves the page

.watch/ is ignored by Git. Nothing in it is ever committed.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
WATCH_DIR = REPO_ROOT / ".watch"
STATE_PATH = WATCH_DIR / "state.json"
OUTPUT_PATH = WATCH_DIR / "output.log"
EVENTS_PATH = WATCH_DIR / "events.jsonl"

MAX_EVENTS = 200

EMPTY_STATE: dict[str, Any] = {
    "run": {
        "label": None,
        "command": None,
        "state": "idle",
        "started": None,
        "finished": None,
        "elapsed": 0.0,
        "percent": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "exit_code": None,
    },
    "history": [],
    "updated": None,
}


def ensure_dir() -> None:
    WATCH_DIR.mkdir(parents=True, exist_ok=True)


def read_state() -> dict[str, Any]:
    """Read the current state, tolerating a half-written file."""
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return json.loads(json.dumps(EMPTY_STATE))


def write_state(state: dict[str, Any]) -> None:
    """Write state atomically, so a reader never sees a partial file."""
    ensure_dir()
    state["updated"] = time.time()
    handle, tmp_name = tempfile.mkstemp(dir=str(WATCH_DIR), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as tmp:
            json.dump(state, tmp)
        os.replace(tmp_name, STATE_PATH)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def append_event(kind: str, text: str) -> None:
    """Add a line to the development timeline."""
    ensure_dir()
    entry = {"t": time.time(), "kind": kind, "text": text}
    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def read_events(limit: int = 40) -> list[dict[str, Any]]:
    """Return the most recent timeline entries, newest first."""
    if not EVENTS_PATH.is_file():
        return []
    try:
        lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    events = []
    for line in lines[-MAX_EVENTS:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(events))[:limit]


def read_output(limit: int = 400) -> list[str]:
    """Return the tail of the current run output."""
    if not OUTPUT_PATH.is_file():
        return []
    try:
        text = OUTPUT_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[-limit:]
