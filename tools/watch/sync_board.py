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

# What a search has to ask for before this can build a correct board.
# `priority` and `duedate` only affect the order within a column, so a
# board without them is untidy rather than wrong; the two below change
# which tickets are counted at all.
REQUIRED_FIELDS = ("issuetype", "key", "status", "summary")


def _issue_nodes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the issue list out of either response shape."""
    issues = payload.get("issues")
    if isinstance(issues, dict):
        return issues.get("nodes", [])
    if isinstance(issues, list):
        return issues
    raise ValueError("no issues found; expected {'issues': [...]} or {'issues': {'nodes': [...]}}")


def check_fields_are_present(issues: list[dict[str, Any]]) -> None:
    """Refuse a search result that is missing a field the board filters on.

    `build_board` drops epics by `issuetype` and ignores the
    administrative tickets by key. A search that did not ask for
    `issuetype` returns issues with no type at all, so no epic is
    recognised and all nine are counted as development tickets - which
    does not fail, does not warn, and quietly changes the denominator
    the percentage is built on.

    That happened: the same board synced as "46 development tickets, 46%
    done" from one search and "55 development tickets, 42% done" from
    another, minutes apart, with nothing on the board changed in between.
    A panel whose job is to let somebody see the board without opening
    Jira has to be wrong loudly or not at all.
    """
    if not issues:
        return
    missing = [name for name in ("issuetype", "status") if not any(i.get(name) for i in issues)]
    if missing:
        raise ValueError(
            f"no issue carries {' or '.join(missing)}, so the board cannot be built "
            f"correctly - the search needs to ask for "
            f"{', '.join(sorted(REQUIRED_FIELDS))}"
        )


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
        nodes = _issue_nodes(payload)
        check_fields_are_present([node.get("fields", {}) for node in nodes])
        issues = [normalise(raw) for raw in nodes]
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
