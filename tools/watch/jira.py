"""The Jira board, for the watcher page.

The board reaches the page one of two ways.

**Agent-synced (the default, no setup).** The assistant already reads Jira
through the Atlassian MCP server as it works, so it writes what it sees to
.watch/board.json. The board on the page is then the board the agent is
working from, and it changes the moment a ticket is moved rather than on a
polling interval. Nothing here needs a credential.

**Live (opt-in).** Set JIRA_EMAIL and JIRA_API_TOKEN in .env and this module
polls Jira itself every 60 seconds, writing the same file. Useful when you
want the board to keep updating while the agent is not running.

Both produce the same shape, so the page does not care which is in use; it
just says which one it is looking at.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from state import WATCH_DIR, write_json_atomic

BOARD_PATH = WATCH_DIR / "board.json"

SITE = "jkwakyi.atlassian.net"
PROJECT = "ON"
BOARD_URL = f"https://{SITE}/jira/software/projects/{PROJECT}"

COLUMNS = ["Backlog", "To Do", "In Progress", "Done"]

# Administrative tickets that are not development work; the board rules say
# to ignore them, so they are left out of the counts as well.
IGNORED = {
    "ON-28",
    "ON-30",
    "ON-31",
    "ON-35",
    "ON-50",
    "ON-53",
    "ON-55",
    "ON-57",
    "ON-58",
    "ON-59",
    "ON-60",
    "ON-61",
}

POLL_SECONDS = 60
FIELDS = "summary,status,priority,duedate,issuetype,parent"


def load_board() -> dict[str, Any] | None:
    """Return the current board snapshot, or None if there is not one yet."""
    try:
        return json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_board(board: dict[str, Any]) -> None:
    board["synced"] = time.time()
    write_json_atomic(BOARD_PATH, board)


def empty_board(source: str = "agent") -> dict[str, Any]:
    return {
        "source": source,
        "project": PROJECT,
        "url": BOARD_URL,
        "columns": {name: [] for name in COLUMNS},
        "counts": {name: 0 for name in COLUMNS},
    }


def build_board(issues: list[dict[str, Any]], source: str) -> dict[str, Any]:
    """Group issues into board columns.

    `issues` are plain dicts with key, summary, status, priority, duedate,
    type and optionally epic — the same whichever source produced them.
    """
    board = empty_board(source)
    for issue in issues:
        if issue["key"] in IGNORED or issue.get("type") == "Epic":
            continue
        status = issue.get("status")
        if status in board["columns"]:
            board["columns"][status].append(issue)

    priority_rank = {"Highest": 0, "High": 1, "Medium": 2, "Low": 3, "Lowest": 4}
    for name, items in board["columns"].items():
        items.sort(key=lambda i: (priority_rank.get(i.get("priority"), 9), i.get("duedate") or "9"))
        board["counts"][name] = len(items)

    total = sum(board["counts"].values())
    done = board["counts"]["Done"]
    board["total"] = total
    board["percent_done"] = round(done / total * 100) if total else 0
    return board


# --- live polling (only when credentials are configured) ---------------


def _credentials() -> tuple[str, str] | None:
    email = os.environ.get("JIRA_EMAIL", "").strip()
    token = os.environ.get("JIRA_API_TOKEN", "").strip()
    return (email, token) if email and token else None


def _fetch_issues(email: str, token: str) -> list[dict[str, Any]]:
    """Fetch the project's issues from the Jira REST API."""
    query = urllib.parse.urlencode(
        {
            "jql": f'project = "{PROJECT}" ORDER BY priority, duedate',
            "fields": FIELDS,
            "maxResults": 100,
        }
    )
    request = urllib.request.Request(f"https://{SITE}/rest/api/3/search/jql?{query}")
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    request.add_header("Authorization", f"Basic {auth}")
    request.add_header("Accept", "application/json")

    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    issues = []
    for raw in payload.get("issues", []):
        fields = raw.get("fields", {})
        issues.append(
            {
                "key": raw["key"],
                "summary": fields.get("summary", ""),
                "status": (fields.get("status") or {}).get("name"),
                "priority": (fields.get("priority") or {}).get("name"),
                "duedate": fields.get("duedate"),
                "type": (fields.get("issuetype") or {}).get("name"),
                "epic": (fields.get("parent") or {}).get("key"),
                "url": f"https://{SITE}/browse/{raw['key']}",
            }
        )
    return issues


def _poll_forever() -> None:
    credentials = _credentials()
    if not credentials:
        return
    email, token = credentials
    while True:
        try:
            save_board(build_board(_fetch_issues(email, token), "live"))
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            existing = load_board() or empty_board("live")
            existing["error"] = f"{type(exc).__name__}: {exc}"
            save_board(existing)
        time.sleep(POLL_SECONDS)


def start_polling_if_configured() -> bool:
    """Start the live poller when credentials are set. Returns whether it did."""
    if not _credentials():
        return False
    thread = threading.Thread(target=_poll_forever, name="jira-poll", daemon=True)
    thread.start()
    return True
