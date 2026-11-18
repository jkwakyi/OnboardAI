"""Extracting the text and splitting it into sections (ON-40, step U3).

The other half of the Document Upload Service: "extracts text from the file
and splits it into sections", which are then saved to the Main Database and
passed on to be turned into vectors (ON-41).

A section is the unit the whole assistant is built on. It is what gets a
vector, what retrieval returns five of, what the LLM Gateway is allowed to
quote, and what a citation points at. So the split is not a detail of
storage: a section that runs across two unrelated policies produces a
citation that is half right, and one cut through the middle of a sentence
produces an answer that trails off. The aim is a section a person would
recognise as "the bit of the handbook that answers this".

Bounded on purpose
------------------
TD-22 said this ticket owed the other half of the upload limit: ON-39
bounds what arrives, and nothing bounded what it would cost to read. A PDF
is a program of sorts, and a small one can ask for a great deal of work.
So extraction stops at a page count, at a character count, and at a wall
clock, and says which of the three it hit.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from app.services.documents.storage import PDF, TXT, UploadRefused

logger = logging.getLogger(__name__)


class UnreadableDocument(UploadRefused):
    """The file is a valid PDF or TXT and there is no usable text in it.

    The case this exists for is a scanned PDF: a photograph of a page, with
    no text layer. Storing it would leave an HR administrator believing the
    assistant can answer from a document it cannot read a word of.
    """


@dataclass(frozen=True)
class SectionText:
    """One section, before it becomes a database row."""

    position: int
    heading: str | None
    text: str


# --- extraction --------------------------------------------------------


def extract_text(
    path: Path,
    content_type: str,
    *,
    max_pages: int,
    max_characters: int,
    timeout_seconds: float,
) -> str:
    """The text of a stored document, or a refusal."""
    if content_type == TXT:
        return _extract_txt(path, max_characters=max_characters)
    if content_type == PDF:
        return _extract_pdf(
            path,
            max_pages=max_pages,
            max_characters=max_characters,
            timeout_seconds=timeout_seconds,
        )
    raise UnreadableDocument(f"There is no way to read a {content_type} document.")


# Encodings to try, in order. UTF-8 first because it is what anything
# written this decade uses; cp1252 second because it is what Word on
# Windows produces and is the common second answer; latin-1 last because it
# cannot fail, which makes it a terminator rather than a guess.
TEXT_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


def _extract_txt(path: Path, *, max_characters: int) -> str:
    raw = path.read_bytes()
    for encoding in TEXT_ENCODINGS:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if encoding != TEXT_ENCODINGS[0]:
            logger.info("read %s as %s rather than UTF-8", path.name, encoding)
        return _bounded(text, max_characters, path)
    # latin-1 decodes any byte sequence, so this is unreachable unless the
    # list above changes. Kept so that it fails loudly if it ever does.
    raise UnreadableDocument("That text file is not in a readable encoding.")


def _extract_pdf(path: Path, *, max_pages: int, max_characters: int, timeout_seconds: float) -> str:
    # Imported here rather than at module import: pypdf is only needed when
    # a PDF actually arrives, and keeping it out of the import graph of
    # every test that touches this package keeps the suite quick.
    from pypdf import PdfReader

    # PyPdfError is the base of every error pypdf raises on its own
    # account; catching it rather than the half-dozen subclasses means
    # a new one in a later version is still a refusal rather than a 500.
    from pypdf.errors import PyPdfError

    started = time.monotonic()
    try:
        reader = PdfReader(path)
        pages = reader.pages
    except (PyPdfError, OSError, ValueError) as broken:
        raise UnreadableDocument(
            "That PDF could not be opened. It may be damaged or encrypted."
        ) from broken

    if len(pages) > max_pages:
        logger.info("%s has %d pages; reading the first %d", path.name, len(pages), max_pages)

    collected: list[str] = []
    length = 0
    for number, page in enumerate(pages[:max_pages], start=1):
        # Checked per page rather than once at the end: the point is to
        # stop doing the work, not to find out afterwards that it was done.
        if time.monotonic() - started > timeout_seconds:
            logger.warning(
                "stopped reading %s after %.1fs at page %d", path.name, timeout_seconds, number
            )
            break
        try:
            page_text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - one bad page is not a bad document
            logger.warning("could not read page %d of %s", number, path.name, exc_info=True)
            continue
        collected.append(page_text)
        length += len(page_text)
        if length >= max_characters:
            logger.info("stopped reading %s at the %d character limit", path.name, max_characters)
            break

    text = "\n\n".join(collected)
    if not text.strip():
        raise UnreadableDocument(
            "No text could be read from that PDF. If it is a scan, it needs to "
            "be run through text recognition before it can be uploaded."
        )
    return _bounded(text, max_characters, path)


def _bounded(text: str, max_characters: int, path: Path) -> str:
    if len(text) <= max_characters:
        return text
    logger.info("truncated %s to %d characters", path.name, max_characters)
    # Cut at a line boundary where there is one nearby, so the last section
    # does not end mid-word.
    cut = text.rfind("\n", 0, max_characters)
    return text[: cut if cut > max_characters // 2 else max_characters]


# --- splitting ---------------------------------------------------------

# A numbered heading: "5.1 ELIGIBILITY AND ENROLMENT", "2.4.1 Pay".
#
# The dot is required, and that is the whole point of this pattern (ON-69).
# It used to accept a bare number too - "3 Scope" - which also matched every
# line of an ordinary numbered list. The handbook lists its eleven company
# holidays as "1. New Year's Day", "4. Juneteenth" and so on, so each became
# a heading with nothing under it, and a heading with no body was dropped.
# Eleven holidays were stored nowhere, and an employee asking whether
# Juneteenth is a holiday got nothing from a handbook that says it is.
#
# A document that really does use bare numbers for its headings now loses
# those divisions and is split at paragraphs instead. That is the trade the
# module's own rule points at: a missed heading merges two sections, which
# is survivable, while a false one swallows the text beneath it.
NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)+\.?\s+\S")

# A Markdown heading, for anybody who uploads notes rather than a handbook.
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+\S")

# A line of rule characters, which documents use to separate sections and
# which carries no text of its own.
RULE = re.compile(r"^[-=_*~]{3,}$")

# A heading is short. A paragraph that happens to start with a number is
# not a heading, and this is what tells them apart.
MAX_HEADING_LENGTH = 90


def looks_like_a_heading(line: str) -> bool:
    """Is this line a heading rather than a sentence?

    Three signals, any of which is enough: it is numbered, it is Markdown,
    or it is short and shouted. Deliberately conservative - a missed
    heading merges two sections, which is survivable, while a false one
    chops a paragraph in half and gives a citation a title that is really
    the middle of a sentence.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_HEADING_LENGTH:
        return False
    if MARKDOWN_HEADING.match(stripped):
        return True
    if NUMBERED_HEADING.match(stripped) and not stripped.endswith((".", ",", ";")):
        return True
    letters = [character for character in stripped if character.isalpha()]
    if len(letters) >= 3 and all(character.isupper() for character in letters):
        return True
    return False


def clean_heading(line: str) -> str:
    """A heading as it should be stored and shown in a citation."""
    return re.sub(r"^#{1,6}\s*", "", line.strip()).strip()


def split_into_sections(
    text: str, *, max_characters: int, min_characters: int
) -> list[SectionText]:
    """Split extracted text into the sections retrieval will search.

    Headings first, because a document that has them has already been
    divided by the person who wrote it, and their divisions are better than
    any this could invent. A section too long to be one retrieval result is
    then split again at paragraph boundaries, each piece keeping the
    heading so a citation still names where it came from.
    """
    blocks = _blocks_by_heading(text)

    pieces: list[tuple[str | None, str]] = []
    for heading, body in blocks:
        body = body.strip()
        if not body:
            # A heading with nothing under it. Dropping it threw the
            # heading's own words away with it, which is how the handbook's
            # holidays went missing (ON-69). Fold it into the section above
            # so the text survives; if there is no section above, hold it
            # for the next one.
            if heading:
                _carry_heading_text(pieces, heading)
            continue
        for part in _split_long_body(body, max_characters):
            pieces.append((heading, part))

    pieces = _merge_crumbs(pieces, min_characters, max_characters)

    return [
        SectionText(position=position, heading=heading, text=body)
        for position, (heading, body) in enumerate(pieces)
    ]


def _blocks_by_heading(text: str) -> list[tuple[str | None, str]]:
    """(heading, body) pairs, in the order they appear.

    Text before the first heading is a block with no heading: a preamble is
    still something somebody may ask about.
    """
    blocks: list[tuple[str | None, list[str]]] = [(None, [])]
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if RULE.match(line.strip()):
            continue
        if looks_like_a_heading(line):
            blocks.append((clean_heading(line), []))
        else:
            blocks[-1][1].append(line)
    return [(heading, "\n".join(lines)) for heading, lines in blocks]


def _split_long_body(body: str, max_characters: int) -> list[str]:
    """Break a body too long for one section, at paragraph boundaries.

    A paragraph that is itself longer than the limit is passed through
    whole rather than cut: a sentence split down the middle reads as a
    broken answer, and one oversized section reads as a long one.
    """
    if len(body) <= max_characters:
        return [body]

    parts: list[str] = []
    current: list[str] = []
    length = 0
    for paragraph in re.split(r"\n\s*\n", body):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and length + len(paragraph) > max_characters:
            parts.append("\n\n".join(current))
            current, length = [], 0
        current.append(paragraph)
        length += len(paragraph) + 2
    if current:
        parts.append("\n\n".join(current))
    return parts


def _carry_heading_text(pieces: list[tuple[str | None, str]], heading: str) -> None:
    """Keep the words of a heading that had no section under it.

    Appended to the section above, because that is where a reader would
    find it on the page. With nothing above it yet, it becomes a piece of
    its own and the next merge will join it to what follows.
    """
    if pieces:
        last_heading, last_body = pieces[-1]
        pieces[-1] = (last_heading, f"{last_body}\n{heading}")
    else:
        pieces.append((None, heading))


def _join(first: tuple[str | None, str], second: tuple[str | None, str]) -> tuple[str | None, str]:
    """Join two pieces, keeping the heading of whichever brought more text.

    Two sections joined used to keep the first one's heading whatever its
    size, so a one-line crumb could put its title on the long section that
    followed - and the citation then pointed at the wrong place (ON-69).
    The longer piece is what the joined text is mostly about.

    The heading that loses keeps its words: they go into the body at the
    point they appeared in the document. Otherwise fixing a misleading
    citation would quietly delete a line of the handbook, which is the
    same failure in a different place.
    """
    first_heading, first_body = first
    second_heading, second_body = second

    if len(first_body) >= len(second_body):
        kept = first_heading or second_heading
        dropped = second_heading if second_heading and second_heading != kept else None
        body = f"{first_body}\n\n{dropped}\n{second_body}" if dropped else None
    else:
        kept = second_heading or first_heading
        dropped = first_heading if first_heading and first_heading != kept else None
        body = f"{dropped}\n{first_body}\n\n{second_body}" if dropped else None

    return kept, body if body is not None else f"{first_body}\n\n{second_body}"


def _merge_crumbs(
    pieces: list[tuple[str | None, str]], min_characters: int, max_characters: int
) -> list[tuple[str | None, str]]:
    """Fold a too-short section into the one after it.

    A heading on its own, or a one-line note, is not something retrieval
    can match on usefully - it has too few words to carry meaning - and it
    costs an embedding each. Merging forward keeps the heading with the
    text it introduces, which is the direction that makes sense: a heading
    belongs to what follows it.
    """
    merged: list[tuple[str | None, str]] = []
    pending: tuple[str | None, str] | None = None

    for heading, body in pieces:
        if pending is not None:
            joined_heading, joined_body = _join(pending, (heading, body))
            if len(joined_body) <= max_characters:
                heading, body = joined_heading, joined_body
            else:
                merged.append(pending)
            pending = None
        if len(body) < min_characters:
            pending = (heading, body)
            continue
        merged.append((heading, body))

    if pending is not None:
        # Nothing followed it. Attach it to the previous section if that
        # leaves a section of a sensible size, or keep it as its own.
        if merged and len(merged[-1][1]) + len(pending[1]) <= max_characters:
            merged[-1] = _join(merged[-1], pending)
        else:
            merged.append(pending)

    return merged


__all__ = [
    "MAX_HEADING_LENGTH",
    "TEXT_ENCODINGS",
    "SectionText",
    "UnreadableDocument",
    "clean_heading",
    "extract_text",
    "looks_like_a_heading",
    "split_into_sections",
]
