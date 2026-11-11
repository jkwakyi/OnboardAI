"""Serve the OnboardAI development watcher page.

    python tools/watch/watch_server.py [--port 8777]

Then open http://127.0.0.1:8777.

The page shows what is actually happening: the current test run with its live
output, the git state of the checkout, whether each service is reachable, and
a timeline of what has run. It binds to the loopback interface only.

Nothing here is part of the product. It reads the repository and the files in
.watch/; it never writes to either.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from jira import load_board, start_polling_if_configured
from state import REPO_ROOT, read_events, read_output, read_state

HOST = "127.0.0.1"
DEFAULT_PORT = 8777
PAGE = Path(__file__).resolve().parent / "index.html"

# Service name -> port, from docker-compose.yml and the README run steps.
SERVICES = {
    "PostgreSQL": 5432,
    "ChromaDB": 8001,
    "Backend API": 8000,
    "Frontend": 5173,
}

RE_TICKET = re.compile(r"(ON-\d+)")

_git_cache: dict[str, Any] = {"at": 0.0, "value": None}
GIT_CACHE_SECONDS = 2.0


def _git(*args: str) -> str:
    """Run a git command in the repository, returning stripped stdout."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _changed_files() -> list[str]:
    """Paths of uncommitted changes, from `git status --porcelain`.

    Parsed from unstripped output on purpose: a porcelain line is two status
    characters then a space then the path, and an unstaged change leaves the
    first character blank. Stripping the output would eat that leading space
    on the first line only, losing a character from one filename.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []

    paths = []
    for line in result.stdout.splitlines():
        match = re.match(r"^(..) (.+)$", line)
        if match:
            paths.append(match.group(2))
    return paths


def git_state() -> dict[str, Any]:
    """Branch, head commit, working tree cleanliness and remote position."""
    now = time.time()
    if _git_cache["value"] is not None and now - _git_cache["at"] < GIT_CACHE_SECONDS:
        return _git_cache["value"]

    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    dirty_files = _changed_files()

    ahead = behind = None
    tracking = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if tracking:
        counts = _git("rev-list", "--left-right", "--count", f"{tracking}...HEAD")
        parts = counts.split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])

    ticket = RE_TICKET.search(branch or "")

    value = {
        "branch": branch or "(unknown)",
        "sha": _git("rev-parse", "--short", "HEAD"),
        "subject": _git("log", "-1", "--pretty=%s"),
        "committed": _git("log", "-1", "--pretty=%cr"),
        "dirty": len(dirty_files),
        "dirty_files": dirty_files[:12],
        "tracking": tracking or None,
        "ahead": ahead,
        "behind": behind,
        "ticket": ticket.group(1) if ticket else None,
        "ticket_url": (
            f"https://jkwakyi.atlassian.net/browse/{ticket.group(1)}" if ticket else None
        ),
        "recent": [
            {"sha": line[:7], "subject": line[8:]}
            for line in _git("log", "-8", "--pretty=%h %s").splitlines()
        ],
    }
    _git_cache.update(at=now, value=value)
    return value


def _port_open(port: int, timeout: float = 0.25) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((HOST, port)) == 0


def services_state() -> list[dict[str, Any]]:
    return [{"name": name, "port": port, "up": _port_open(port)} for name, port in SERVICES.items()]


@lru_cache(maxsize=1)
def _handbook_count() -> int:
    return len(list((REPO_ROOT / "data" / "handbook" / "txt").glob("*.txt")))


def repo_state() -> dict[str, Any]:
    """A few cheap facts about the project, so the page is useful when idle."""
    backend_tests = list((REPO_ROOT / "backend" / "tests").glob("test_*.py"))
    return {
        "handbook_documents": _handbook_count(),
        "backend_test_files": len(backend_tests),
    }


def build_state() -> dict[str, Any]:
    state = read_state()
    run = state.get("run", {})

    # Keep the elapsed clock moving while a run is in flight, even between
    # the writes run.py makes.
    if run.get("state") == "running" and run.get("started"):
        run["elapsed"] = time.time() - run["started"]

    return {
        "now": time.time(),
        "run": run,
        "history": state.get("history", []),
        "output": read_output(),
        "events": read_events(),
        "git": git_state(),
        "services": services_state(),
        "repo": repo_state(),
        "board": load_board(),
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        if self.path.startswith("/api/state"):
            body = json.dumps(build_state()).encode("utf-8")
            self._send(body, "application/json; charset=utf-8")
            return

        if self.path in ("/", "/index.html"):
            try:
                body = PAGE.read_bytes()
            except OSError:
                self._send(b"index.html is missing", "text/plain; charset=utf-8", 500)
                return
            self._send(body, "text/html; charset=utf-8")
            return

        self._send(b"not found", "text/plain; charset=utf-8", 404)

    def log_message(self, *args: Any) -> None:
        """Stay quiet; the page polls once a second."""


def _load_dotenv() -> None:
    """Read .env into the environment, without adding a dependency.

    Only fills in names that are not already set, so a real environment
    variable always wins over the file.
    """
    env_path = REPO_ROOT / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def _already_listening(port: int) -> bool:
    """True if something is already serving on this port.

    Windows lets a 127.0.0.1 bind succeed alongside an existing 0.0.0.0 bind,
    so checking that we can bind is not enough: we have to check that nobody
    answers. Starting quietly behind another server is worse than refusing.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((HOST, port)) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OnboardAI development watcher")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    port = parser.parse_args().port

    if _already_listening(port):
        print(
            f"Port {port} is already in use on {HOST}. Something else is serving "
            f"there, so the watcher would be shadowed. Start it on another port:\n\n"
            f"    python tools/watch/watch_server.py --port {port + 1}\n",
            file=sys.stderr,
        )
        return 1

    _load_dotenv()
    live = start_polling_if_configured()

    server = ThreadingHTTPServer((HOST, port), Handler)
    print(f"OnboardAI watcher on http://{HOST}:{port}  (Ctrl-C to stop)", flush=True)
    print(
        "Jira board: polling live"
        if live
        else "Jira board: agent-synced (set JIRA_EMAIL and JIRA_API_TOKEN in .env to poll live)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
