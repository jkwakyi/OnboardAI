"""The synthetic handbook corpus is complete, readable and consistent.

The handbook is the approved document set OnboardAI answers from, and the
input for the evaluation question set (ON-23) and the alpha smoke test
(ON-26). These tests guard three things:

* every document exists in both TXT and PDF, and the PDF is readable;
* the specific facts the evaluation questions rely on are still present;
* the deliberate gaps are still gaps, so the HR fallback path stays testable.

The last one matters most. Filling a gap silently would make an unanswerable
evaluation question answerable and quietly weaken the fallback coverage.
"""

import re

import pytest
from pypdf import PdfReader

from app.config import REPO_ROOT

pytestmark = pytest.mark.handbook

HANDBOOK_DIR = REPO_ROOT / "data" / "handbook"
TXT_DIR = HANDBOOK_DIR / "txt"
PDF_DIR = HANDBOOK_DIR / "pdf"

TXT_FILES = sorted(TXT_DIR.glob("*.txt"))

# One checkable fact per document, drawn from the table in the handbook README.
# If an edit drops one of these, an evaluation question loses its answer.
REQUIRED_FACTS = [
    ("01-welcome-and-company-overview", "Portland, Oregon"),
    ("02-employment-policies", "90 calendar days"),
    ("02-employment-policies", "10:00 to 16:00 Eastern Time"),
    ("03-compensation-and-payroll", "semi-monthly"),
    ("03-compensation-and-payroll", "2,000 US dollars"),
    ("04-time-off-and-leave", "15 days per year"),
    ("04-time-off-and-leave", "11 paid company holidays"),
    ("04-time-off-and-leave", "12 weeks at full pay"),
    ("05-benefits-and-wellbeing", "4 per cent of base salary"),
    ("05-benefits-and-wellbeing", "75 US dollars per month"),
    ("06-code-of-conduct", "100 US dollars or less"),
    ("06-code-of-conduct", "10 business days"),
    ("07-it-security-and-acceptable-use", "at least 14 characters"),
    ("07-it-security-and-acceptable-use", "Restricted"),
    ("07-it-security-and-acceptable-use", "within one hour"),
    ("08-onboarding-training-and-performance", "April and October"),
    ("08-onboarding-training-and-performance", "60 days"),
    ("08-onboarding-training-and-performance", "1,500 US dollars"),
]

# Subjects the corpus must NOT cover, so ON-23 can write questions the
# assistant has to answer with the HR fallback. Each entry is a regular
# expression searched across the whole corpus, case-insensitively.
DELIBERATE_GAPS = {
    "stock options or equity": r"stock option|equity grant|share scheme|RSU",
    "sales commission": r"commission (plan|structure|rate)",
    "jury duty": r"jury duty",
    "military leave": r"military leave",
    "relocation assistance": r"relocation (assistance|allowance|package)",
    "severance": r"severance",
    "visa sponsorship": r"visa|immigration sponsorship|work permit",
    "commuter benefits": r"commuter benefit|parking (space|permit|allowance)",
    "sabbatical": r"sabbatical",
    "childcare subsidy": r"childcare (subsidy|benefit)|backup care",
    "tuition reimbursement": r"tuition",
    "pets in the office": r"\bpets?\b",
}


def _read(path) -> str:
    return path.read_text(encoding="utf-8")


def _corpus() -> str:
    return "\n".join(_read(p) for p in TXT_FILES)


def test_corpus_is_present():
    assert TXT_FILES, f"no handbook TXT files found in {TXT_DIR}"


def test_document_count_matches_the_architecture_diagram():
    """The diagram calls for a fake company handbook of 6 to 8 documents."""
    assert 6 <= len(TXT_FILES) <= 8, f"found {len(TXT_FILES)} documents"


@pytest.mark.parametrize("txt_path", TXT_FILES, ids=lambda p: p.stem)
def test_every_document_has_a_pdf(txt_path):
    """The contracts accept PDF and TXT, so the corpus ships both."""
    assert (PDF_DIR / f"{txt_path.stem}.pdf").is_file()


def test_no_orphan_pdfs():
    """A PDF with no TXT source means someone edited the generated output."""
    stems = {p.stem for p in TXT_FILES}
    orphans = sorted(p.name for p in PDF_DIR.glob("*.pdf") if p.stem not in stems)
    assert orphans == [], f"PDFs without a TXT source: {orphans}"


@pytest.mark.parametrize("txt_path", TXT_FILES, ids=lambda p: p.stem)
def test_pdf_is_readable_and_matches_its_source(txt_path):
    """Text extracted from the PDF carries the same content as the TXT.

    Upload accepts either format, so the sections extracted from one should be
    equivalent to the sections extracted from the other.
    """
    reader = PdfReader(PDF_DIR / f"{txt_path.stem}.pdf")
    assert len(reader.pages) >= 1

    extracted = " ".join(page.extract_text() or "" for page in reader.pages)
    extracted = re.sub(r"\s+", " ", extracted)

    # Every non-trivial source line should survive the round trip.
    source_lines = [
        line.strip()
        for line in _read(txt_path).splitlines()
        if len(line.strip()) > 25 and not line.strip().startswith("-----")
    ]
    assert source_lines, "document has no substantial lines"

    missing = [line for line in source_lines if re.sub(r"\s+", " ", line) not in extracted]
    assert missing == [], f"lines lost in the PDF: {missing[:3]}"


@pytest.mark.parametrize("txt_path", TXT_FILES, ids=lambda p: p.stem)
def test_every_document_says_it_is_fictional(txt_path):
    """No real employee or company data: each document states it outright."""
    assert "fictional company" in _read(txt_path)


@pytest.mark.parametrize("stem,fact", REQUIRED_FACTS, ids=lambda v: str(v)[:40])
def test_required_facts_are_present(stem, fact):
    """Facts the evaluation questions depend on are still in the corpus."""
    path = TXT_DIR / f"{stem}.txt"
    assert fact in _read(path), f"{fact!r} missing from {path.name}"


def test_enough_facts_for_twenty_answerable_questions():
    """The ticket needs room for 20 answerable questions."""
    assert len(REQUIRED_FACTS) >= 20 or len(set(REQUIRED_FACTS)) >= 18


@pytest.mark.parametrize("subject,pattern", sorted(DELIBERATE_GAPS.items()))
def test_deliberate_gaps_stay_empty(subject, pattern):
    """These subjects are intentionally absent so the HR fallback is testable.

    Adding one here makes an unanswerable evaluation question answerable.
    Update ON-23 before changing this.
    """
    hits = re.findall(pattern, _corpus(), flags=re.IGNORECASE)
    assert hits == [], f"corpus now covers {subject!r}: found {sorted(set(hits))}"


def test_enough_gaps_for_ten_unanswerable_questions():
    """The ticket needs room for 10 unanswerable questions."""
    assert len(DELIBERATE_GAPS) >= 10
