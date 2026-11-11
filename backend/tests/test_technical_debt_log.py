"""The technical debt log stays structurally sound as entries are added.

The log is only useful if every entry actually says what was done, why, what
it costs and how it gets paid back. An entry missing one of those is the
shape of entry that reads as an apology and tells a reader nothing.

These tests check structure, not honesty. Whether an impact is stated
truthfully is a judgement only the team can make; what a test can do is make
sure nobody can add a half-filled entry, let the index drift out of step with
the sections, or invent a status.
"""

import re

import pytest

from app.config import REPO_ROOT

LOG_PATH = REPO_ROOT / "TECHNICAL-DEBT.md"
TEXT = LOG_PATH.read_text(encoding="utf-8")

REQUIRED_FIELDS = ["What", "Why", "Impact", "Mitigation"]
VALID_STATUSES = {"Open", "Accepted", "Mitigated"}

RE_SECTION = re.compile(r"^### (TD-\d+) — (.+)$", re.MULTILINE)
RE_INDEX_ROW = re.compile(
    r"^\| \[(TD-\d+)\]\(#([^)]+)\) \| (.+?) \| (.+?) \| (.+?) \|$", re.MULTILINE
)
RE_STATUS = re.compile(r"\*\*Status:\*\* (\w+)")


def _anchor(heading: str) -> str:
    """The anchor GitHub generates for a heading."""
    slug = re.sub(r"[^a-z0-9 \-]", "", heading.lower())
    return slug.replace(" ", "-")


def _sections() -> dict[str, dict[str, str]]:
    """Split the log into entries: id -> {title, body}."""
    matches = list(RE_SECTION.finditer(TEXT))
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(TEXT)
        sections[match.group(1)] = {
            "title": match.group(2).strip(),
            "body": TEXT[match.end() : end],
        }
    return sections


SECTIONS = _sections()
INDEX_ROWS = {m.group(1): m for m in RE_INDEX_ROW.finditer(TEXT)}
ENTRY_IDS = sorted(SECTIONS)


def test_the_log_exists_and_has_entries():
    assert LOG_PATH.is_file()
    assert SECTIONS, "the log has no entries"


def test_entry_ids_are_unique_and_consecutive():
    """TD-01, TD-02, ... with no gaps and no reused numbers."""
    numbers = sorted(int(entry_id.split("-")[1]) for entry_id in SECTIONS)
    assert numbers == list(range(1, len(numbers) + 1)), f"ids are not consecutive: {numbers}"


@pytest.mark.parametrize("entry_id", ENTRY_IDS)
def test_every_entry_states_what_why_impact_and_mitigation(entry_id):
    """All four fields are the point of the log; an entry missing one is noise."""
    body = SECTIONS[entry_id]["body"]
    missing = [field for field in REQUIRED_FIELDS if f"**{field}.**" not in body]
    assert missing == [], f"{entry_id} is missing: {missing}"


@pytest.mark.parametrize("entry_id", ENTRY_IDS)
def test_every_field_has_content(entry_id):
    """A field heading with nothing after it would pass the check above."""
    body = SECTIONS[entry_id]["body"]
    for field in REQUIRED_FIELDS:
        match = re.search(rf"\*\*{field}\.\*\*(.*?)(?=\n\n|\Z)", body, re.DOTALL)
        assert match and len(match.group(1).strip()) > 30, (
            f"{entry_id}: '{field}' is empty or too short to say anything"
        )


@pytest.mark.parametrize("entry_id", ENTRY_IDS)
def test_every_entry_has_a_valid_status(entry_id):
    status = RE_STATUS.search(SECTIONS[entry_id]["body"])
    assert status, f"{entry_id} has no status"
    assert status.group(1) in VALID_STATUSES, (
        f"{entry_id}: status {status.group(1)!r} is not one of {sorted(VALID_STATUSES)}"
    )


@pytest.mark.parametrize("entry_id", ENTRY_IDS)
def test_every_entry_records_when_it_was_taken(entry_id):
    assert "**Taken:**" in SECTIONS[entry_id]["body"], f"{entry_id} does not say when"


# --- the index and the sections agree ----------------------------------


def test_index_lists_every_entry():
    assert set(INDEX_ROWS) == set(SECTIONS), (
        f"in the index but not below: {sorted(set(INDEX_ROWS) - set(SECTIONS))}; "
        f"below but not in the index: {sorted(set(SECTIONS) - set(INDEX_ROWS))}"
    )


@pytest.mark.parametrize("entry_id", ENTRY_IDS)
def test_index_link_points_at_the_real_heading(entry_id):
    expected = _anchor(f"{entry_id} — {SECTIONS[entry_id]['title']}")
    linked = INDEX_ROWS[entry_id].group(2)
    assert linked == expected, (
        f"{entry_id}: index links to #{linked}, the heading anchor is #{expected}"
    )


@pytest.mark.parametrize("entry_id", ENTRY_IDS)
def test_index_status_matches_the_entry(entry_id):
    """A status changed in one place and not the other is a quiet lie."""
    in_section = RE_STATUS.search(SECTIONS[entry_id]["body"]).group(1)
    in_index = INDEX_ROWS[entry_id].group(5).strip()
    assert in_index == in_section, (
        f"{entry_id}: index says {in_index!r}, the entry says {in_section!r}"
    )


@pytest.mark.parametrize("entry_id", ENTRY_IDS)
def test_index_title_matches_the_heading(entry_id):
    assert INDEX_ROWS[entry_id].group(3).strip() == SECTIONS[entry_id]["title"]


# --- references --------------------------------------------------------


@pytest.mark.parametrize("entry_id", ENTRY_IDS)
def test_ticket_references_are_well_formed(entry_id):
    """Catches ON23 or ON-/ typos that would not link anywhere."""
    body = SECTIONS[entry_id]["body"]
    for reference in re.findall(r"\bON[-\s]?\d*\b", body):
        assert re.fullmatch(r"ON-\d+", reference), (
            f"{entry_id}: {reference!r} is not a well-formed ticket key"
        )
