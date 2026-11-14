"""The Mock Embedder (ON-41).

It exists so CI and teammates with no key can run the system, which means
the thing worth testing is not that it embeds well - it cannot - but that
it embeds *consistently*, at the right width, and with enough lexical
signal for retrieval to be exercised at all.
"""

import math

import pytest

from app.config import Settings
from app.services.embedding.mock import MockEmbedder, tokenise

# What a single word's bucket holds once the vector is scaled to unit
# length, when two words landed in two different buckets: 1/sqrt(2).
SQRT_HALF = math.sqrt(0.5)


def embedder(width: int = 64) -> MockEmbedder:
    return MockEmbedder(Settings(embedding_provider="mock", embedding_dimensions=width))


def cosine(left, right) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


# --- shape -------------------------------------------------------------


def test_every_vector_has_the_configured_width():
    vectors = embedder(width=128).embed(["one", "two"])

    assert [len(vector) for vector in vectors] == [128, 128]


def test_one_vector_per_text_in_the_same_order():
    first, second = embedder().embed(["parental leave", "travel expenses"])

    assert first != second
    assert embedder().embed(["parental leave"])[0] == first


def test_no_texts_means_no_vectors():
    assert embedder().embed([]) == []


def test_vectors_are_unit_length():
    # Cosine similarity is a dot product only when both sides are unit
    # length, and ChromaDB's default space compares with cosine distance.
    (vector,) = embedder().embed(["Annual leave accrues monthly."])

    assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0, rel_tol=1e-9)


# --- determinism -------------------------------------------------------


def test_the_same_text_always_gives_the_same_vector():
    assert embedder().embed(["sick leave"]) == embedder().embed(["sick leave"])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("sick leave", {53: -SQRT_HALF, 58: -SQRT_HALF}),
        ("parental leave", {40: -SQRT_HALF, 53: -SQRT_HALF}),
    ],
)
def test_the_vector_does_not_depend_on_the_process(text, expected):
    """The real hazard: `hash()` is salted per process in Python.

    A mock built on `hash()` would pass every other test in this file and
    still give different vectors on every run - a collection written by
    one process would be meaningless to the next, and the symptom would be
    retrieval that worked until the server restarted.

    These buckets were captured from a separate process (and confirmed
    identical under three different `PYTHONHASHSEED` values). Recomputing
    them here, in a process that has its own salt, is what makes this a
    cross-process check rather than a restatement of the code.

    Note which bucket is shared: 53 is "leave" in both. That is the whole
    lexical mechanism, visible.
    """
    (vector,) = embedder(width=64).embed([text])
    nonzero = {index: value for index, value in enumerate(vector) if value}

    assert nonzero.keys() == expected.keys()
    for index, value in expected.items():
        assert math.isclose(nonzero[index], value, rel_tol=1e-9)


# --- lexical signal ----------------------------------------------------


def test_texts_sharing_words_are_closer_than_texts_that_share_none():
    about_leave_one = "Parental leave is twelve weeks of paid leave."
    about_leave_two = "Paid parental leave lasts twelve weeks."
    about_expenses = "Travel receipts must be submitted within thirty days."

    one, two, other = embedder(width=256).embed([about_leave_one, about_leave_two, about_expenses])

    assert cosine(one, two) > cosine(one, other)


def test_punctuation_and_capitals_do_not_change_the_vector():
    plain, shouted = embedder().embed(["parental leave", "Parental, LEAVE!"])

    assert plain == shouted


def test_numbers_are_words_too():
    # "30 days" and "90 days" differ by the only part that matters.
    thirty, ninety = embedder(width=256).embed(["notice of 30 days", "notice of 90 days"])

    assert thirty != ninety


@pytest.mark.parametrize("text", ["", "   ", "!!! ???"])
def test_a_text_with_no_words_still_gets_a_usable_vector(text):
    # Not a vector of zeros: it has no direction, cosine against it is
    # undefined, and ChromaDB would return nonsense distances for it.
    (vector,) = embedder().embed([text])

    assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0, rel_tol=1e-9)


# --- tokenising --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Parental Leave", ["parental", "leave"]),
        ("e-mail HR", ["e", "mail", "hr"]),
        ("30 days", ["30", "days"]),
        ("", []),
    ],
)
def test_tokenise(text, expected):
    assert tokenise(text) == expected
