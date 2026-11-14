"""File Storage: keeping the original uploaded file (ON-39, step U2).

The Document Upload Service "saves the original file to File Storage (U2)".
This is that half of it. Extracting the text and splitting it into sections
is ON-40, and nothing here reads the file's contents beyond the few bytes
it takes to tell a PDF from a text file.

Three things decide whether an upload is kept, and all three are refusals
rather than corrections: the file is a PDF or a TXT, it is not empty, and
it is not larger than the configured limit. Quietly fixing an upload - by
truncating it, or by deciding a file named .pdf must be one - would mean
the HR administrator believes they approved something other than what is
now searchable.

The name on disk is ours
------------------------
`stored_path` is a name this module generates. The uploaded filename is
kept in the database for display and never used to build a path: a
filename is attacker-controlled text, and the whole family of bugs where
`../../etc/something` ends up being written is avoided by never putting it
in a path in the first place, rather than by sanitising it well.
"""

from __future__ import annotations

import logging
import re
import secrets
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

logger = logging.getLogger(__name__)

# The contracts allow PDF and TXT and nothing else.
PDF = "pdf"
TXT = "txt"

# What a browser is likely to declare for each. The declaration is a hint
# that narrows the choice; it is never the thing that decides, because a
# client sets it and a client can be wrong or lying.
DECLARED_TYPES: dict[str, str] = {
    "application/pdf": PDF,
    "application/x-pdf": PDF,
    "text/plain": TXT,
    "text/markdown": TXT,
}

EXTENSIONS: dict[str, str] = {".pdf": PDF, ".txt": TXT, ".text": TXT, ".md": TXT}

# Every PDF begins with this. A file that claims to be one and does not is
# refused rather than stored and discovered later by ON-40.
PDF_MAGIC = b"%PDF-"

# How much of the file to look at before deciding what it is.
SNIFF_BYTES = 1024

# Read the upload in pieces rather than into memory. 64 KiB is large enough
# that the loop is not the cost and small enough that a hundred concurrent
# uploads are not either.
CHUNK_BYTES = 64 * 1024

# Characters that have no business in a stored display name. Control
# characters above all: a filename containing a newline breaks every log
# line that quotes it.
_UNSAFE_NAME = re.compile(r"[\x00-\x1f\x7f/\\]")
MAX_FILENAME_LENGTH = 255


class UploadRefused(Exception):
    """The upload was not stored, and this is what to tell the uploader.

    The message is written to be read by an HR administrator looking at an
    upload page, not by a developer looking at a log.

    The three subclasses name *why* without naming an HTTP status code.
    The service has no business knowing what a 415 is, and the API has no
    business reading an error message to find out what happened - which is
    what it would be reduced to if there were only one class here.
    """


class UnsupportedDocument(UploadRefused):
    """Not a PDF or a TXT, whatever it was called."""


class DocumentTooLarge(UploadRefused):
    """Over the configured size limit."""


class UnusableDocument(UploadRefused):
    """Empty, or with no name to store it under."""


@dataclass(frozen=True)
class StoredFile:
    """What was written, and what to record about it."""

    path: Path
    filename: str
    content_type: str
    size_bytes: int


def safe_filename(raw: str | None) -> str:
    """The uploaded name, cleaned up for storing and showing.

    Not used to build a path - see the module docstring. This is about what
    an HR administrator reads back in the document list, so it keeps as
    much of their name as is safe to render and nothing that is not.
    """
    name = unicodedata.normalize("NFKC", (raw or "").strip())
    # Only the last component: a browser sending a path is sending
    # something the person never typed.
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = _UNSAFE_NAME.sub("", name).strip(". ")
    if not name:
        raise UnusableDocument("The file needs a name.")
    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, suffix = name.rpartition(".")
        keep = MAX_FILENAME_LENGTH - len(dot) - len(suffix)
        name = f"{stem[:keep]}{dot}{suffix}" if dot else name[:MAX_FILENAME_LENGTH]
    return name


def detect_content_type(filename: str, declared: str | None, head: bytes) -> str:
    """PDF, TXT, or a refusal.

    The order is deliberate. What the bytes say beats what the client said,
    because only one of those two is evidence.
    """
    if head.startswith(PDF_MAGIC):
        return PDF

    suffix = Path(filename).suffix.lower()
    declared_kind = DECLARED_TYPES.get((declared or "").split(";")[0].strip().lower())
    extension_kind = EXTENSIONS.get(suffix)

    if declared_kind == PDF or extension_kind == PDF:
        # It says PDF and does not begin like one. Storing it would mean
        # ON-40 finding out, after the HR administrator was told it worked.
        raise UnsupportedDocument(
            "That file is named like a PDF but does not contain one. "
            "Please upload the original PDF."
        )

    if declared_kind == TXT or extension_kind == TXT:
        if b"\x00" in head:
            # Nothing a person typed contains a NUL byte. Something that
            # does is a binary file wearing a .txt.
            raise UnsupportedDocument(
                "That file is named like a text file but contains binary data. "
                "Please upload a PDF or a plain text file."
            )
        return TXT

    raise UnsupportedDocument("Only PDF and TXT documents can be uploaded.")


def _chunks(stream, size: int = CHUNK_BYTES) -> Iterator[bytes]:
    while True:
        chunk = stream.read(size)
        if not chunk:
            return
        yield chunk


def save_upload(
    stream,
    *,
    filename: str | None,
    declared_content_type: str | None,
    directory: Path,
    max_bytes: int,
) -> StoredFile:
    """Write an upload to File Storage, or refuse it.

    The size limit is applied while writing rather than by trusting the
    Content-Length header, because the header is also something the client
    sets. The partial file is removed on any refusal: a half-written
    document in File Storage is one ON-40 would eventually index.
    """
    name = safe_filename(filename)

    head = stream.read(SNIFF_BYTES)
    if not head:
        raise UnusableDocument("That file is empty.")
    content_type = detect_content_type(name, declared_content_type, head)

    directory.mkdir(parents=True, exist_ok=True)
    # A name of our own: unguessable, collision-free, and carrying nothing
    # the uploader chose.
    path = directory / f"{secrets.token_hex(16)}.{content_type}"

    written = 0
    try:
        with path.open("wb") as handle:
            # chain, not `(head, *_chunks(stream))`: unpacking a
            # generator into a tuple runs it to completion first, which
            # reads the whole upload into memory before the size check
            # below has seen a single byte. That turns the limit into
            # something that is enforced only after the damage is done.
            for chunk in chain((head,), _chunks(stream)):
                written += len(chunk)
                if written > max_bytes:
                    raise DocumentTooLarge(
                        f"That file is larger than the {max_bytes // (1024 * 1024)} MB limit."
                    )
                handle.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise

    logger.info("stored %s (%s, %d bytes) as %s", name, content_type, written, path.name)
    return StoredFile(path=path, filename=name, content_type=content_type, size_bytes=written)


def delete_stored_file(path: Path) -> None:
    """Remove a stored file, for a save that could not be finished.

    Missing is success: this is called to make sure the file is not there,
    and a file that was never written satisfies that.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # Worth a line in the log and not worth failing a request over: the
        # database row is the thing that decides what exists.
        logger.warning("could not remove %s from File Storage", path, exc_info=True)


__all__ = [
    "CHUNK_BYTES",
    "DECLARED_TYPES",
    "EXTENSIONS",
    "MAX_FILENAME_LENGTH",
    "PDF",
    "PDF_MAGIC",
    "SNIFF_BYTES",
    "TXT",
    "DocumentTooLarge",
    "StoredFile",
    "UnsupportedDocument",
    "UnusableDocument",
    "UploadRefused",
    "delete_stored_file",
    "detect_content_type",
    "safe_filename",
    "save_upload",
]
