"""Break one thing at a time and check a test notices.

Every ticket in this repository ends with a pass of this: a list of
single-edit faults, each applied to the working tree on its own, with the
relevant tests run against it. A fault no test notices is a test that was
not testing anything, and finding that out is the point.

    python tools/inject/inject.py faults/ON-45.py

A faults file sets `TESTS` (what to run), `FAULTS` (a list of
`(description, path, before, after)`) and, for the frontend, `ROOT` and
`RUNNER`. Paths are relative to `ROOT`, which defaults to `backend`.

Why this exists as a file rather than being retyped per ticket
-------------------------------------------------------------
Three times across ON-39, ON-40 and ON-45 the throwaway version of this
script was itself the bug, and twice it cost real work:

* It read files with `read_text` and wrote them with `write_text`, which
  turns LF into CRLF on Windows. Every restored file then showed as
  modified, and in ON-40 "tidying up" one of those diffs reverted a real
  change.
* It compared a `before` string containing `\\n` against a file containing
  `\\r\\n`, so every *multi-line* fault silently matched nothing. Six faults
  in ON-45 were reported as skipped rather than applied, which reads a lot
  like a pass if you are scanning the column.
* A `before` string typed from memory, or written before `ruff format`
  reflowed the file, matches nothing for the same reason.

So: files are read with their newlines normalised and written back with the
ones they had, and **a skip is a failure**. A fault that could not be
applied proves nothing, and the exit code says so.
"""

from __future__ import annotations

import argparse
import atexit
import importlib.util
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():  # Linux, and CI
    PYTHON = BACKEND / ".venv" / "bin" / "python"


# The one file that currently has a fault in it, so it can be put back if
# this process is killed. A `finally` does not run when the process is
# terminated, and a fault left in the tree is worse than no pass at all -
# it is a broken source file somebody then has to notice. Learned the hard
# way: a `timeout 240` around this left a mutated gateway.py behind.
_applied: tuple[Path, str, str] | None = None


def _restore_applied(*_signal_arguments: object) -> None:
    global _applied
    if _applied is None:
        return
    path, original, newline = _applied
    _applied = None
    write(path, original, newline)
    print(f"restored {path} on the way out", file=sys.stderr, flush=True)


atexit.register(_restore_applied)
for _signal in (signal.SIGINT, signal.SIGTERM):
    signal.signal(_signal, lambda *arguments: (_restore_applied(), sys.exit(130)))


@dataclass
class Outcome:
    caught: list[str]
    missed: list[str]
    skipped: list[str]

    @property
    def ok(self) -> bool:
        return not self.missed and not self.skipped


def read(path: Path) -> tuple[str, str]:
    """The file's text with LF newlines, and the newline it actually uses.

    Normalising on the way in is what makes a multi-line `before` string
    match on a CRLF file. Returning the original newline is what puts the
    file back exactly as it was.
    """
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8").replace("\r\n", "\n"), newline


def write(path: Path, text: str, newline: str) -> None:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def command_for(runner: str, target: str) -> list[str]:
    if runner == "pytest":
        return [
            str(PYTHON), "-m", "pytest", target,
            "-q", "-x", "--no-header", "-p", "no:cacheprovider",
        ]
    if runner == "vitest":
        # `npx` rather than a path, because node_modules/.bin differs
        # between Windows and the Linux CI runs.
        return ["npx", "--yes", "vitest", "run", target, "--silent"]
    raise ValueError(f"unknown runner: {runner!r}")


def run(runner: str, root: Path, target: str) -> bool:
    """True if the tests pass."""
    result = subprocess.run(
        command_for(runner, target),
        cwd=root,
        capture_output=True,
        text=True,
        # Explicit, because the default on Windows is the console's code
        # page - cp1252 here - and vitest prints box-drawing characters.
        # The reader thread then dies with a UnicodeDecodeError part way
        # through, which is both noisy and untrustworthy: a crashed reader
        # can leave this reporting a result the test run never gave.
        encoding="utf-8",
        errors="replace",
        shell=(runner == "vitest"),
    )
    return result.returncode == 0


def load_faults(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return (
        module.TESTS,
        module.FAULTS,
        getattr(module, "RUNNER", "pytest"),
        REPO / getattr(module, "ROOT", "backend"),
    )


def inject(runner: str, root: Path, tests: str, faults: list[tuple[str, str, str, str]]) -> Outcome:
    outcome = Outcome([], [], [])

    for description, relative, before, after in faults:
        path = root / relative
        original, newline = read(path)

        if before not in original:
            print(f"   SKIP  {description}", flush=True)
            print(f"         the text to break is not in {relative} - fix the fault", flush=True)
            outcome.skipped.append(description)
            continue
        if before == after:
            print(f"   SKIP  {description}: the fault changes nothing", flush=True)
            outcome.skipped.append(description)
            continue

        global _applied
        _applied = (path, original, newline)
        write(path, original.replace(before, after, 1), newline)
        try:
            caught = not run(runner, root, tests)
        finally:
            write(path, original, newline)
            _applied = None

        print(f" {'caught' if caught else 'MISSED':>6}  {description}", flush=True)
        (outcome.caught if caught else outcome.missed).append(description)

    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("faults", type=Path, help="a faults file (see tools/inject/faults/)")
    arguments = parser.parse_args(argv)

    tests, faults, runner, root = load_faults(arguments.faults)

    if not run(runner, root, tests):
        print(f"{tests} does not pass before any fault is injected.", file=sys.stderr)
        return 2

    outcome = inject(runner, root, tests, faults)

    total = len(faults)
    print(f"\n{len(outcome.caught)}/{total} faults caught", flush=True)
    if outcome.missed:
        print(f"{len(outcome.missed)} went unnoticed by the tests:", file=sys.stderr)
        for description in outcome.missed:
            print(f"  - {description}", file=sys.stderr)
    if outcome.skipped:
        # Not a pass. A fault that could not be applied proves nothing.
        print(f"{len(outcome.skipped)} could not be applied:", file=sys.stderr)
        for description in outcome.skipped:
            print(f"  - {description}", file=sys.stderr)

    if not run(runner, root, tests):
        print(f"{tests} does not pass after restoring the files.", file=sys.stderr)
        return 2

    return 0 if outcome.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
