"""Reading a document and splitting it into sections (ON-40, U3).

A section is what gets a vector, what retrieval returns five of, and what a
citation points at. So these tests are mostly about the split rather than
the reading: a section running across two unrelated policies produces a
citation that is half right, and one cut through a sentence produces an
answer that trails off.

The real handbook in `data/handbook` is the corpus, so what is checked is
the splitter against documents the assistant will actually be asked about.
"""

import time
from pathlib import Path

import pytest

from app.config import REPO_ROOT, Settings
from app.services.documents.extraction import (
    MAX_HEADING_LENGTH,
    SectionText,
    UnreadableDocument,
    clean_heading,
    extract_text,
    looks_like_a_heading,
    split_into_sections,
)

HANDBOOK = REPO_ROOT / "data" / "handbook"
BENEFITS_TXT = HANDBOOK / "txt" / "05-benefits-and-wellbeing.txt"
BENEFITS_PDF = HANDBOOK / "pdf" / "05-benefits-and-wellbeing.pdf"

SETTINGS = Settings()


def read(path: Path, content_type: str, **overrides) -> str:
    options = {
        "max_pages": SETTINGS.pdf_max_pages,
        "max_characters": SETTINGS.extraction_max_characters,
        "timeout_seconds": SETTINGS.extraction_timeout_seconds,
    }
    options.update(overrides)
    return extract_text(path, content_type, **options)


def sections_of(text: str, **overrides) -> list[SectionText]:
    options = {
        "max_characters": SETTINGS.section_max_characters,
        "min_characters": SETTINGS.section_min_characters,
    }
    options.update(overrides)
    return split_into_sections(text, **options)


# --- reading a text file -----------------------------------------------


def test_a_text_document_is_read_whole():
    text = read(BENEFITS_TXT, "txt")

    assert "401(k)" in text
    assert "ELIGIBILITY AND ENROLMENT" in text
    assert len(text) == len(BENEFITS_TXT.read_text(encoding="utf-8"))


def test_a_byte_order_mark_is_not_left_in_the_text(tmp_path):
    """A BOM at the front of a file becomes an invisible character at the
    front of the first section, and then at the front of a citation."""
    path = tmp_path / "notes.txt"
    path.write_bytes(b"\xef\xbb\xbf1.1 HOLIDAY\n\nTwenty days a year.\n")

    text = read(path, "txt")

    assert text.startswith("1.1 HOLIDAY")


def test_a_file_saved_by_word_on_windows_is_still_read(tmp_path):
    """cp1252, which is what a curly quote out of Word is encoded as and
    which is not valid UTF-8."""
    path = tmp_path / "notes.txt"
    path.write_bytes("1.1 HOLIDAY\n\nThe company’s policy.\n".encode("cp1252"))

    text = read(path, "txt")

    assert "company" in text and "policy" in text


def test_an_unknown_content_type_is_refused(tmp_path):
    path = tmp_path / "notes.odt"
    path.write_bytes(b"something")

    with pytest.raises(UnreadableDocument):
        read(path, "odt")


# --- reading a PDF -----------------------------------------------------


def test_a_pdf_is_read():
    text = read(BENEFITS_PDF, "pdf")

    assert "401(k)" in text or "401" in text
    assert len(text) > 500


def test_a_pdf_with_no_text_layer_is_refused(tmp_path):
    """The case this exists for: a scan. Storing it would leave an HR
    administrator believing the assistant can answer from a document it
    cannot read a word of."""
    from reportlab.pdfgen import canvas

    path = tmp_path / "scan.pdf"
    page = canvas.Canvas(str(path))
    page.rect(100, 100, 200, 200, fill=0)  # a drawing, no text
    page.save()

    with pytest.raises(UnreadableDocument, match="text recognition"):
        read(path, "pdf")


def test_a_damaged_pdf_is_refused(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not the rest of a pdf")

    with pytest.raises(UnreadableDocument):
        read(path, "pdf")


def test_only_the_first_pages_are_read(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "long.pdf"
    page = canvas.Canvas(str(path))
    for number in range(10):
        page.drawString(100, 700, f"PAGE MARKER {number}")
        page.showPage()
    page.save()

    text = read(path, "pdf", max_pages=3)

    assert "PAGE MARKER 0" in text
    assert "PAGE MARKER 9" not in text


def test_reading_stops_at_the_character_limit(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "long.pdf"
    page = canvas.Canvas(str(path))
    for _ in range(10):
        page.drawString(100, 700, "x" * 200)
        page.showPage()
    page.save()

    text = read(path, "pdf", max_characters=300)

    assert len(text) <= 300


def test_reading_stops_at_the_wall_clock(tmp_path, monkeypatch):
    """TD-22's other half: a file crafted to be expensive to parse must
    stop costing, not merely be measured afterwards."""
    from reportlab.pdfgen import canvas

    path = tmp_path / "long.pdf"
    page = canvas.Canvas(str(path))
    for number in range(10):
        page.drawString(100, 700, f"PAGE MARKER {number}")
        page.showPage()
    page.save()

    ticks = iter([0.0, 0.0, 0.5, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks, 99.0))

    text = read(path, "pdf", timeout_seconds=10)

    assert "PAGE MARKER 0" in text
    assert "PAGE MARKER 9" not in text


# --- what a heading looks like -----------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "5.1 ELIGIBILITY AND ENROLMENT",
        "5.1 Eligibility and enrolment",
        "3 Scope",
        "2.4.1 Pay dates",
        "# Holiday",
        "### Sick leave",
        "MEDICAL AND DENTAL COVER",
        "NOTICE",
    ],
)
def test_a_heading_is_recognised(line):
    assert looks_like_a_heading(line) is True


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "Regular full-time employees are eligible for the benefits in this document.",
        "1. The company pays 80 per cent of the premium for employee-only cover.",
        "There are 30 days to enrol.",
        "Two medical plans are offered, a Standard plan and a High Deductible plan.",
        "x" * (MAX_HEADING_LENGTH + 1),
    ],
)
def test_a_sentence_is_not(line):
    assert looks_like_a_heading(line) is False


def test_a_markdown_heading_loses_its_hashes():
    assert clean_heading("###  Sick leave ") == "Sick leave"


def test_a_numbered_heading_keeps_its_number():
    """The number is how somebody finds it in the document they were sent."""
    assert clean_heading("5.1 ELIGIBILITY AND ENROLMENT") == "5.1 ELIGIBILITY AND ENROLMENT"


# --- splitting the real handbook ---------------------------------------


def test_the_handbook_splits_on_its_own_headings():
    sections = sections_of(read(BENEFITS_TXT, "txt"))
    headings = [section.heading for section in sections if section.heading]

    assert any(heading.startswith("5.1") for heading in headings)
    assert any(heading.startswith("5.2") for heading in headings)
    assert any(heading.startswith("5.3") for heading in headings)


def test_every_section_has_text_in_it():
    for section in sections_of(read(BENEFITS_TXT, "txt")):
        assert section.text.strip()


def test_no_section_is_longer_than_the_limit():
    """Except an oversized single paragraph, which is passed through whole
    rather than cut through a sentence."""
    sections = sections_of(read(BENEFITS_TXT, "txt"), max_characters=800)

    for section in sections:
        paragraphs = section.text.split("\n\n")
        assert len(section.text) <= 800 or len(paragraphs) == 1


def test_positions_run_from_zero_without_gaps():
    """The Vector Database stores an embedding under a section's id, and
    (document_id, position) is unique - a gap or a repeat is a row that
    will not insert."""
    sections = sections_of(read(BENEFITS_TXT, "txt"))

    assert [section.position for section in sections] == list(range(len(sections)))


def test_the_text_before_the_first_heading_is_not_thrown_away():
    """A preamble is still something somebody may ask about."""
    sections = sections_of("Larkfield Systems handbook, revision 4.2.\n\n1.1 WELCOME\n\nHello.")

    assert any("revision 4.2" in section.text for section in sections)


def test_every_section_of_every_handbook_document_is_usable():
    """Across the whole corpus, not just the one file the splitter was
    looked at with."""
    for path in sorted((HANDBOOK / "txt").glob("*.txt")):
        sections = sections_of(read(path, "txt"))

        assert sections, f"{path.name} produced no sections"
        assert [s.position for s in sections] == list(range(len(sections)))
        for section in sections:
            assert section.text.strip(), f"{path.name} has an empty section"


# --- the shape of the split --------------------------------------------


def test_a_long_body_is_split_at_paragraph_boundaries():
    body = "\n\n".join(f"Paragraph {number} about the policy." for number in range(40))

    sections = sections_of(f"1.1 POLICY\n\n{body}", max_characters=300, min_characters=50)

    assert len(sections) > 1
    for section in sections:
        # Nothing was cut mid-sentence.
        assert section.text.endswith(".")


def test_each_piece_of_a_split_body_keeps_the_heading():
    """Otherwise the second half of a long policy produces a citation with
    no title, which is a citation nobody can look up."""
    body = "\n\n".join(f"Paragraph {number} about the policy." for number in range(40))

    sections = sections_of(f"1.1 POLICY\n\n{body}", max_characters=300, min_characters=50)

    assert all(section.heading == "1.1 POLICY" for section in sections)


def test_a_heading_on_its_own_is_folded_into_what_follows_it():
    """A heading with no body has too few words for retrieval to match on,
    and costs an embedding each."""
    text = "1.1 HOLIDAY\n\n1.2 SICK LEAVE\n\n" + "Five days a year is the entitlement. " * 20

    sections = sections_of(text)

    assert len(sections) == 1
    assert "entitlement" in sections[0].text


def test_a_rule_line_is_not_mistaken_for_content():
    text = "1.1 HOLIDAY\n\n" + "-" * 79 + "\n\nTwenty days a year. " * 20

    sections = sections_of(text)

    assert all("---" not in section.text for section in sections)


def test_a_document_with_no_headings_still_splits():
    body = "\n\n".join(f"A paragraph of policy text, number {number}." for number in range(60))

    sections = sections_of(body, max_characters=400, min_characters=100)

    assert len(sections) > 1
    assert all(section.heading is None for section in sections)


@pytest.mark.parametrize("empty", ["", "   ", "\n\n\n", "-------"])
def test_nothing_in_produces_nothing_out(empty):
    assert sections_of(empty) == []


# --- the bounds stop work rather than merely trimming output -----------


def test_the_character_limit_stops_the_loop_rather_than_trimming_at_the_end(tmp_path):
    """There are two bounds on characters and only one of them matters.

    Truncating the text afterwards keeps the output small; stopping the
    loop is what keeps the work small. A fault that removed the break went
    unnoticed until this test existed, because the final truncation made
    the result look identical.
    """
    from reportlab.pdfgen import canvas

    path = tmp_path / "long.pdf"
    page = canvas.Canvas(str(path))
    for number in range(20):
        page.drawString(100, 700, f"PAGE MARKER {number} " + "x" * 150)
        page.showPage()
    page.save()

    read_pages = []
    original = __import__("pypdf").PageObject.extract_text

    def counting(self, *args, **kwargs):
        text = original(self, *args, **kwargs)
        read_pages.append(text)
        return text

    import pypdf

    pypdf.PageObject.extract_text = counting
    try:
        read(path, "pdf", max_characters=300)
    finally:
        pypdf.PageObject.extract_text = original

    assert len(read_pages) < 20, "every page was read despite the character limit"


def test_a_long_numbered_paragraph_is_not_a_heading():
    """The length guard is what tells a heading from a paragraph that
    happens to start with a clause number."""
    line = (
        "5.1 of this document applies to regular full-time employees who have "
        "completed their probationary period and remain in good standing"
    )
    assert len(line) > MAX_HEADING_LENGTH

    assert looks_like_a_heading(line) is False


def test_a_short_section_is_folded_into_the_next_one():
    """Not an empty one - an empty body is dropped anyway, which is what
    made the earlier version of this test pass without exercising the
    merge at all."""
    short = "Applies to everyone."
    long_enough = "Five days a year is the entitlement. " * 20
    text = f"1.1 SCOPE\n\n{short}\n\n1.2 SICK LEAVE\n\n{long_enough}"

    sections = sections_of(text, min_characters=200, max_characters=1500)

    assert len(sections) == 1
    assert short in sections[0].text
    assert "entitlement" in sections[0].text


def test_a_short_section_with_nothing_after_it_is_still_kept():
    """Merging forward has nowhere to go for the last one, and dropping it
    would lose text somebody may ask about."""
    sections = sections_of("1.1 SCOPE\n\nApplies to everyone.", min_characters=200)

    assert len(sections) == 1
    assert "Applies to everyone." in sections[0].text


def test_a_document_of_nothing_but_rule_lines_produces_no_sections(tmp_path):
    """Reachable, which is why `index_document` refuses it: a TXT file of
    separators is not empty as bytes, so it reaches the splitter."""
    path = tmp_path / "rules.txt"
    path.write_text("-----\n=====\n-----\n", encoding="utf-8")

    assert sections_of(read(path, "txt")) == []
