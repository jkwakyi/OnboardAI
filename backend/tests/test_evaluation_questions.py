"""The evaluation question set is well formed and grounded in the handbook.

These tests do not run the assistant; that is ON-24. They check that the
question set is a trustworthy yardstick before anything is measured against
it, because a wrong expected answer or a stale section reference would show
up later as a model failure rather than as a mistake in the test data.

Every answerable question is checked against the handbook text itself:

* the source document exists;
* the source section exists in that document;
* a quoted supporting sentence really appears there;
* every number in the expected answer appears in that document.

Every unanswerable question is checked against the deliberate gaps ON-12
records, so an unanswerable question can never quietly become answerable.
"""

import json
import re

import pytest

from app.config import REPO_ROOT
from tests.test_handbook import DELIBERATE_GAPS, TXT_DIR

pytestmark = pytest.mark.handbook

QUESTIONS_PATH = REPO_ROOT / "data" / "evaluation" / "questions.json"

DATA = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
QUESTIONS = DATA["questions"]
ANSWERABLE = [q for q in QUESTIONS if q["answerable"]]
UNANSWERABLE = [q for q in QUESTIONS if not q["answerable"]]


def _normalise(text: str) -> str:
    """Collapse whitespace so a quote spanning a line break still matches."""
    return re.sub(r"\s+", " ", text).strip()


def _document(name: str) -> str:
    return _normalise((TXT_DIR / name).read_text(encoding="utf-8"))


def _ids(questions):
    return [q["id"] for q in questions]


# --- shape -------------------------------------------------------------


def test_there_are_thirty_questions():
    assert len(QUESTIONS) == 30


def test_exactly_ten_are_unanswerable():
    assert len(UNANSWERABLE) == 10
    assert len(ANSWERABLE) == 20


def test_declared_counts_match_the_questions():
    counts = DATA["counts"]
    assert counts["total"] == len(QUESTIONS)
    assert counts["answerable"] == len(ANSWERABLE)
    assert counts["unanswerable"] == len(UNANSWERABLE)


def test_ids_are_unique():
    ids = _ids(QUESTIONS)
    assert len(set(ids)) == len(ids)


def test_questions_are_distinct():
    asked = [q["question"].strip().lower() for q in QUESTIONS]
    assert len(set(asked)) == len(asked)


@pytest.mark.parametrize("question", QUESTIONS, ids=_ids(QUESTIONS))
def test_every_question_is_a_question(question):
    assert question["question"].endswith("?")
    assert question["expected_fallback"] is not question["answerable"]


# --- answerable questions are grounded in the handbook -----------------


@pytest.mark.parametrize("question", ANSWERABLE, ids=_ids(ANSWERABLE))
def test_answerable_questions_carry_an_answer_and_a_source(question):
    """The ticket requires an expected answer and a source section."""
    assert question["expected_answer"].strip()
    assert question["source_document"].strip()
    assert question["source_section"].strip()


@pytest.mark.parametrize("question", ANSWERABLE, ids=_ids(ANSWERABLE))
def test_source_document_exists(question):
    assert (TXT_DIR / question["source_document"]).is_file()


@pytest.mark.parametrize("question", ANSWERABLE, ids=_ids(ANSWERABLE))
def test_source_section_exists_in_that_document(question):
    """Guards against a section reference going stale when text is edited."""
    section = question["source_section"]
    document = _document(question["source_document"])
    assert re.search(rf"\b{re.escape(section)} [A-Z]", document), (
        f"section {section} not found in {question['source_document']}"
    )


@pytest.mark.parametrize("question", ANSWERABLE, ids=_ids(ANSWERABLE))
def test_supporting_text_appears_in_the_source_document(question):
    """The quoted sentence must really be in the handbook."""
    support = _normalise(question["supporting_text"])
    assert support in _document(question["source_document"]), (
        f"{question['id']}: supporting text not found in {question['source_document']}"
    )


@pytest.mark.parametrize("question", ANSWERABLE, ids=_ids(ANSWERABLE))
def test_numbers_in_the_expected_answer_appear_in_the_source(question):
    """A figure in the answer that is not in the handbook is a wrong answer."""
    document = _document(question["source_document"])
    numbers = re.findall(r"\d[\d,:]*", question["expected_answer"])
    missing = [n for n in numbers if n not in document]
    assert missing == [], f"{question['id']}: {missing} not in {question['source_document']}"


def test_answerable_questions_span_every_handbook_document():
    """Coverage should not cluster in two or three documents."""
    used = {q["source_document"] for q in ANSWERABLE}
    everything = {p.name for p in TXT_DIR.glob("*.txt")}
    assert used == everything, f"documents never asked about: {sorted(everything - used)}"


# --- unanswerable questions rest on the deliberate gaps ----------------


@pytest.mark.parametrize("question", UNANSWERABLE, ids=_ids(UNANSWERABLE))
def test_unanswerable_questions_name_a_known_gap(question):
    """Ties each one to a gap ON-12 deliberately left in the corpus."""
    assert question["gap"] in DELIBERATE_GAPS, (
        f"{question['id']}: {question['gap']!r} is not one of the deliberate gaps"
    )


@pytest.mark.parametrize("question", UNANSWERABLE, ids=_ids(UNANSWERABLE))
def test_unanswerable_questions_have_no_expected_answer(question):
    """The expected outcome is the HR fallback, not an answer."""
    assert question["expected_fallback"] is True
    assert "expected_answer" not in question
    assert "source_section" not in question


def test_each_unanswerable_question_uses_a_distinct_gap():
    gaps = [q["gap"] for q in UNANSWERABLE]
    assert len(set(gaps)) == len(gaps), "two questions lean on the same gap"
