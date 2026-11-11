"""Write the watcher's Jira board snapshot from a Jira search result.

The assistant reads Jira through the Atlassian MCP server as it works. That
response is large, so rather than retyping it, it is piped through here:

    python tools/watch/sync_board.py --from <search-result.json>

The input may be either shape, so the same command works for a saved MCP
tool result and for a raw Jira REST response:

    {"issues": {"nodes": [ ... ]}}     the MCP server's shape
    {"issues": [ ... ]}                the REST API's shape

The result is .watch/board.json, which the watcher page reads. It is the same
file the optional live poller writes, so the page does not care which
produced it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jira import SITE, build_board, save_board


def _issue_nodes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the issue list out of either response shape."""
    issues = payload.get("issues")
    if isinstance(issues, dict):
        return issues.get("nodes", [])
    if isinstance(issues, list):
        return issues
    raise ValueError("no issues found; expected {'issues': [...]} or {'issues': {'nodes': [...]}}")


def normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduce one Jira issue to the handful of fields the page shows."""
    fields = raw.get("fields", {})
    return {
        "key": raw["key"],
        "summary": fields.get("summary", ""),
        "status": (fields.get("status") or {}).get("name"),
        "priority": (fields.get("priority") or {}).get("name"),
        "duedate": fields.get("duedate"),
        "type": (fields.get("issuetype") or {}).get("name"),
        "epic": (fields.get("parent") or {}).get("key"),
        "url": raw.get("webUrl") or f"https://{SITE}/browse/{raw['key']}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", required=True, help="the search result JSON")
    args = parser.parse_args()

    path = Path(args.source)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"could not read {path}: {exc}", file=sys.stderr)
        return 1

    try:
        issues = [normalise(raw) for raw in _issue_nodes(payload)]
    except (ValueError, KeyError) as exc:
        print(f"unexpected shape in {path}: {exc}", file=sys.stderr)
        return 1

    board = build_board(issues, source="agent")
    save_board(board)

    counts = board["counts"]
    print(
        f"board synced: {board['total']} development tickets - "
        + ", ".join(f"{name} {counts[name]}" for name in counts)
        + f" ({board['percent_done']}% done)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
