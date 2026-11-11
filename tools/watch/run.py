"""Run a development command and report its progress to the watcher page.

Use it in place of calling the command directly:

    python tools/watch/run.py --label "backend pytest" -- pytest -q
    python tools/watch/run.py --label "frontend tests" --cwd frontend -- npm test

Output is streamed to the terminal as usual and copied to .watch/output.log,
so nothing is hidden by running it this way. Progress is parsed from the
output as it arrives and written to .watch/state.json for the page to read.

Exit code is passed through, so this stays usable in a script or in CI.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from state import OUTPUT_PATH, REPO_ROOT, append_event, ensure_dir, read_state, write_state

# pytest prints a running percentage: "........  [ 32%]"
RE_PYTEST_PERCENT = re.compile(r"\[\s*(\d+)%\]")
# pytest announces the total up front: "collected 67 items"
RE_PYTEST_COLLECTED = re.compile(r"collected (\d+) items?")
# When markers deselect some, "N selected" is the number that will actually run.
RE_PYTEST_SELECTED = re.compile(r"(\d+) selected")
# pytest's summary line, in any order: "67 passed, 2 deselected in 0.55s"
RE_SUMMARY_COUNT = re.compile(r"(\d+) (passed|failed|error|errors|skipped|deselected)")
# vitest: "Tests  2 passed (2)"
RE_VITEST_TESTS = re.compile(r"Tests\s+(?:(\d+) failed[^(]*?)?(?:\|\s*)?(\d+) passed\s*\((\d+)\)")

WRITE_INTERVAL = 0.25


def _resolve_executable(program: str, cwd: str | None) -> str:
    """Turn the command's first word into something CreateProcess accepts.

    A relative path like backend/.venv/Scripts/python.exe is resolved against
    --cwd, then the repository root, then the current directory; a bare name
    like "npm" is looked up on PATH. Without this, whether the command runs
    depends on which directory you happened to be in, which is a poor
    property for a tool everyone is asked to put in front of their commands.
    """
    if any(sep in program for sep in ("/", "\\")):
        bases = [Path(cwd) if cwd else Path.cwd(), REPO_ROOT, Path.cwd()]
        for base in bases:
            candidate = (base / program).resolve()
            if candidate.is_file():
                return str(candidate)

    found = shutil.which(program, path=None)
    if found:
        return found

    # Let subprocess raise its own error, which names the program.
    return program


def _blank_run(label: str, command: str) -> dict[str, Any]:
    return {
        "label": label,
        "command": command,
        "state": "running",
        "started": time.time(),
        "finished": None,
        "elapsed": 0.0,
        "percent": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "exit_code": None,
    }


def _parse(line: str, run: dict[str, Any]) -> None:
    """Update the run dict from one line of output."""
    collected = RE_PYTEST_COLLECTED.search(line)
    if collected:
        run["total"] = int(collected.group(1))
    selected = RE_PYTEST_SELECTED.search(line)
    if selected:
        run["total"] = int(selected.group(1))

    percent = RE_PYTEST_PERCENT.search(line)
    if percent:
        run["percent"] = int(percent.group(1))
        if run["total"]:
            run["passed"] = round(run["total"] * run["percent"] / 100)

    vitest = RE_VITEST_TESTS.search(line)
    if vitest:
        failed, passed, total = vitest.groups()
        run["failed"] = int(failed or 0)
        run["passed"] = int(passed)
        run["total"] = int(total)
        run["percent"] = 100

    # The summary line is authoritative; it overrides the running estimate.
    counts = RE_SUMMARY_COUNT.findall(line)
    if counts and ("passed" in line or "failed" in line or "error" in line):
        for value, word in counts:
            if word == "passed":
                run["passed"] = int(value)
            elif word in ("failed", "error", "errors"):
                run["failed"] = run["failed"] + int(value) if word == "errors" else int(value)
            elif word == "skipped":
                run["skipped"] = int(value)
        run["percent"] = 100
        # pytest -q never prints "collected N items", so the total is only
        # knowable from the summary.
        if not run["total"]:
            run["total"] = run["passed"] + run["failed"] + run["skipped"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="what this run is, shown on the page")
    parser.add_argument("--cwd", default=None, help="directory to run in")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- then the command")
    args = parser.parse_args()

    command = [part for part in args.command if part != "--"]
    if not command:
        parser.error("no command given; put it after --")

    command[0] = _resolve_executable(command[0], args.cwd)

    ensure_dir()
    printable = " ".join(command)
    run = _blank_run(args.label, printable)

    state = read_state()
    state["run"] = run
    state["history"] = []
    write_state(state)
    append_event("run", f"started: {args.label}")

    OUTPUT_PATH.write_text(f"$ {printable}\n", encoding="utf-8")

    process = subprocess.Popen(
        command,
        cwd=args.cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    last_write = 0.0
    with OUTPUT_PATH.open("a", encoding="utf-8") as log:
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()

            before = run["percent"]
            _parse(line.rstrip("\n"), run)
            run["elapsed"] = time.time() - run["started"]

            # Record every change in progress, so a fast suite still draws a
            # curve rather than two points, and throttle only the file writes.
            if run["percent"] != before:
                state["history"].append({"t": run["elapsed"], "percent": run["percent"]})

            now = time.time()
            if now - last_write >= WRITE_INTERVAL:
                last_write = now
                state["run"] = run
                write_state(state)

    exit_code = process.wait()
    run["exit_code"] = exit_code
    run["finished"] = time.time()
    run["elapsed"] = run["finished"] - run["started"]
    run["percent"] = 100
    run["state"] = "passed" if exit_code == 0 else "failed"

    state["run"] = run
    state["history"].append({"t": run["elapsed"], "percent": 100})
    write_state(state)

    outcome = "passed" if exit_code == 0 else f"FAILED (exit {exit_code})"
    detail = f"{run['passed']} passed"
    if run["failed"]:
        detail += f", {run['failed']} failed"
    append_event("run", f"{args.label}: {outcome} - {detail} in {run['elapsed']:.1f}s")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
