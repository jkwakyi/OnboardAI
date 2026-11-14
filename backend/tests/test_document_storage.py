"""File Storage keeps the original upload, or refuses it (ON-39, U2).

The service on its own, with no HTTP around it. What matters here is that
the three refusals are refusals rather than corrections: a truncated file,
or one stored on the strength of its name, would leave an HR administrator
believing they approved something other than what is now searchable.
"""

import io
from pathlib import Path

import pytest

from app.services.documents.storage import (
    MAX_FILENAME_LENGTH,
    PDF,
    SNIFF_BYTES,
    TXT,
    DocumentTooLarge,
    UnsupportedDocument,
    UnusableDocument,
    UploadRefused,
    delete_stored_file,
    detect_content_type,
    safe_filename,
    save_upload,
)

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
TXT_BYTES = b"Employees are enrolled in the medical plan on their first day.\n"


@pytest.fixture
def storage(tmp_path) -> Path:
    return tmp_path / "documents"


def store(storage: Path, data: bytes, *, name="handbook.pdf", declared=None, limit=1_000_000):
    return save_upload(
        io.BytesIO(data),
        filename=name,
        declared_content_type=declared,
        directory=storage,
        max_bytes=limit,
    )


# --- what gets kept ----------------------------------------------------


def test_a_pdf_is_stored_byte_for_byte(storage):
    stored = store(storage, PDF_BYTES, declared="application/pdf")

    assert stored.content_type == PDF
    assert stored.size_bytes == len(PDF_BYTES)
    assert stored.path.read_bytes() == PDF_BYTES


def test_a_text_file_is_stored_byte_for_byte(storage):
    stored = store(storage, TXT_BYTES, name="policy.txt", declared="text/plain")

    assert stored.content_type == TXT
    assert stored.path.read_bytes() == TXT_BYTES


def test_a_file_larger_than_one_read_survives_intact(storage):
    """The upload is written in chunks, so a file spanning several is the
    case where an off-by-one in the loop would show up."""
    big = (b"policy line\n" * 50_000)[: 300 * 1024]

    stored = store(storage, big, name="handbook.txt", limit=1_000_000)

    assert stored.size_bytes == len(big)
    assert stored.path.read_bytes() == big


def test_the_directory_is_created_if_it_is_not_there(storage):
    assert not storage.exists()

    store(storage, PDF_BYTES)

    assert storage.is_dir()


# --- the name on disk is ours ------------------------------------------


def test_the_stored_name_carries_nothing_the_uploader_chose(storage):
    stored = store(storage, PDF_BYTES, name="Q3 Benefits (final) v2.pdf")

    assert stored.filename == "Q3 Benefits (final) v2.pdf"
    assert "Benefits" not in stored.path.name
    assert stored.path.suffix == ".pdf"


def test_two_uploads_of_the_same_name_do_not_collide(storage):
    first = store(storage, PDF_BYTES, name="handbook.pdf")
    second = store(storage, PDF_BYTES, name="handbook.pdf")

    assert first.path != second.path
    assert first.path.exists() and second.path.exists()


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("handbook.pdf", "handbook.pdf"),
        ("  handbook.pdf  ", "handbook.pdf"),
        ("../../../etc/passwd", "passwd"),
        (r"C:\Users\someone\handbook.pdf", "handbook.pdf"),
        ("/absolute/handbook.pdf", "handbook.pdf"),
        ("hand\nbook.pdf", "handbook.pdf"),
        ("hand\x00book.pdf", "handbook.pdf"),
        ("...handbook.pdf", "handbook.pdf"),
    ],
)
def test_a_filename_is_cleaned_before_it_is_stored(given, expected):
    assert safe_filename(given) == expected


def test_a_traversing_name_cannot_reach_outside_the_directory(storage, tmp_path):
    """The belt to the braces. The name is never used to build a path at
    all, so this is checking that the policy held, not that an escape was
    caught."""
    stored = store(storage, PDF_BYTES, name="../../escaped.pdf")

    assert stored.path.parent == storage
    assert not (tmp_path / "escaped.pdf").exists()


@pytest.mark.parametrize("empty", ["", "   ", "...", "/", "\\", "\x00"])
def test_a_file_with_no_usable_name_is_refused(empty):
    with pytest.raises(UnusableDocument):
        safe_filename(empty)


def test_an_absurdly_long_name_is_shortened_but_keeps_its_extension():
    name = safe_filename("x" * 500 + ".pdf")

    assert len(name) <= MAX_FILENAME_LENGTH
    assert name.endswith(".pdf")


# --- what the bytes say beats what the client said ---------------------


def test_a_pdf_is_recognised_by_its_contents_whatever_it_is_called():
    assert detect_content_type("mystery", None, PDF_BYTES) == PDF
    assert detect_content_type("notes.txt", "text/plain", PDF_BYTES) == PDF


def test_a_file_calling_itself_a_pdf_without_being_one_is_refused(storage):
    """Storing it means ON-40 finding out, after the uploader was told it
    worked."""
    with pytest.raises(UnsupportedDocument, match="does not contain one"):
        store(storage, b"this is not a pdf", name="handbook.pdf", declared="application/pdf")

    assert list(storage.glob("*")) == [] if storage.exists() else True


def test_a_binary_file_wearing_a_txt_is_refused(storage):
    with pytest.raises(UnsupportedDocument, match="binary"):
        store(storage, b"MZ\x90\x00\x03\x00", name="notes.txt", declared="text/plain")


@pytest.mark.parametrize(
    ("name", "declared"),
    [
        ("photo.png", "image/png"),
        ("sheet.xlsx", "application/vnd.ms-excel"),
        ("archive.zip", "application/zip"),
        ("script.sh", "application/x-sh"),
        ("handbook", None),
    ],
)
def test_anything_that_is_not_a_pdf_or_a_txt_is_refused(storage, name, declared):
    with pytest.raises(UnsupportedDocument, match="Only PDF and TXT"):
        store(storage, b"some bytes that are neither", name=name, declared=declared)


def test_a_declared_type_with_parameters_is_still_understood(storage):
    stored = store(storage, TXT_BYTES, name="notes.txt", declared="text/plain; charset=utf-8")

    assert stored.content_type == TXT


# --- the refusals ------------------------------------------------------


def test_an_empty_file_is_refused(storage):
    with pytest.raises(UnusableDocument, match="empty"):
        store(storage, b"")


def test_a_file_over_the_limit_is_refused(storage):
    with pytest.raises(DocumentTooLarge, match="larger than"):
        store(storage, b"x" * 5000, name="notes.txt", limit=1024)


def test_a_file_exactly_at_the_limit_is_kept(storage):
    """Off by one here is the difference between a limit and a trap."""
    data = b"x" * 1024

    stored = store(storage, data, name="notes.txt", limit=1024)

    assert stored.size_bytes == 1024


def test_nothing_is_left_behind_when_an_upload_is_refused(storage):
    """A half-written document in File Storage is one ON-40 would index."""
    with pytest.raises(DocumentTooLarge):
        store(storage, b"x" * 5000, name="notes.txt", limit=1024)

    assert list(storage.glob("*")) == []


def test_the_limit_is_applied_while_writing_not_after(storage):
    """A file far larger than the limit must not be written out in full
    first. Reading a gigabyte to then decide against it is how an upload
    endpoint becomes a way to fill a disk."""
    written = []

    class Watching(io.BytesIO):
        def read(self, size=-1):
            chunk = super().read(size)
            written.append(len(chunk))
            return chunk

    with pytest.raises(DocumentTooLarge):
        save_upload(
            Watching(b"x" * (2 * 1024 * 1024)),
            filename="notes.txt",
            declared_content_type="text/plain",
            directory=storage,
            max_bytes=1024,
        )

    assert sum(written) < 2 * 1024 * 1024


def test_every_refusal_is_an_upload_refused():
    """So a caller that wants to handle all of them can, and one that adds
    a fourth cannot forget to say what it is."""
    for refusal in (UnsupportedDocument, DocumentTooLarge, UnusableDocument):
        assert issubclass(refusal, UploadRefused)


# --- removing a stored file --------------------------------------------


def test_a_stored_file_can_be_removed(storage):
    stored = store(storage, PDF_BYTES)

    delete_stored_file(stored.path)

    assert not stored.path.exists()


def test_removing_a_file_that_is_not_there_is_not_an_error(storage):
    delete_stored_file(storage / "never-existed.pdf")


def test_a_file_that_cannot_be_removed_does_not_raise(storage, monkeypatch, caplog):
    """The database row decides what exists. A file that will not delete is
    a line in the log, not a failed request."""
    stored = store(storage, PDF_BYTES)

    def refuse(*args, **kwargs):
        raise OSError("the file is held open by something")

    monkeypatch.setattr(Path, "unlink", refuse)
    with caplog.at_level("WARNING"):
        delete_stored_file(stored.path)

    assert "could not remove" in caplog.text


# --- sniffing ----------------------------------------------------------


def test_only_the_head_of_the_file_is_sniffed(storage):
    """A PDF marker a megabyte in does not make a text file a PDF."""
    data = b"a" * (SNIFF_BYTES * 2) + b"%PDF-1.7"

    stored = store(storage, data, name="notes.txt", declared="text/plain")

    assert stored.content_type == TXT
