"""The Embedding Client itself (ON-41).

U4 - sections in, vectors in the Vector Database - and the question half of
the same client, which the Retrieval Service will use in ON-43.
"""

import pytest

from app.config import Settings
from app.db.models import Section
from app.services.embedding.client import (
    embed_document_sections,
    embed_question,
    text_for_embedding,
)
from app.services.embedding.provider import EmbeddingError, EmbeddingProvider


class Recorder(EmbeddingProvider):
    """A provider that records what it was asked to embed."""

    def __init__(self, vectors=None, width=2):
        self.asked: list[list[str]] = []
        self.vectors = vectors
        self.width = width

    def embed(self, texts):
        self.asked.append(list(texts))
        if self.vectors is not None:
            return self.vectors
        return [[float(index)] * self.width for index in range(len(texts))]


class Broken(EmbeddingProvider):
    def embed(self, texts):
        raise EmbeddingError("the Embedding API answered 429.")


def section(identifier: int, *, position: int = 0, heading=None, text="some text") -> Section:
    return Section(id=identifier, document_id=1, position=position, heading=heading, text=text)


# --- what gets embedded ------------------------------------------------


def test_the_heading_is_embedded_with_the_body():
    # A heading is the most compressed description a section has -
    # "Parental Leave" over a paragraph that never uses either word - so
    # leaving it out throws away the best signal in the document.
    assert text_for_embedding(section(1, heading="Parental Leave", text="Twelve weeks.")) == (
        "Parental Leave\n\nTwelve weeks."
    )


def test_a_section_with_no_heading_is_embedded_as_it_is():
    assert text_for_embedding(section(1, heading=None, text="Twelve weeks.")) == "Twelve weeks."


def test_the_provider_is_asked_for_the_heading_and_body(collection):
    provider = Recorder()

    embed_document_sections([section(1, heading="Leave", text="Twelve weeks.")], provider=provider)

    assert provider.asked == [["Leave\n\nTwelve weeks."]]


# --- U4 ----------------------------------------------------------------


def test_it_stores_one_vector_per_section(collection):
    sections = [section(1), section(2, position=1), section(3, position=2)]

    written = embed_document_sections(sections, provider=Recorder(), collection=collection)

    assert written == 3
    assert set(collection.rows) == {"1", "2", "3"}


def test_each_section_keeps_its_own_vector(collection):
    # The order the provider returns is the order it was asked in, so the
    # first section gets the first vector. If that ever stopped being
    # true, every citation would point at the wrong paragraph and nothing
    # would raise.
    sections = [section(1), section(2, position=1)]
    provider = Recorder(vectors=[[1.0, 1.0], [2.0, 2.0]])

    embed_document_sections(sections, provider=provider, collection=collection)

    assert collection.vector_for("1") == [1.0, 1.0]
    assert collection.vector_for("2") == [2.0, 2.0]


def test_a_document_with_no_sections_asks_the_provider_for_nothing(collection):
    provider = Recorder()

    assert embed_document_sections([], provider=provider, collection=collection) == 0
    assert provider.asked == []


def test_a_provider_returning_the_wrong_number_of_vectors_is_refused(collection):
    # The interface promises one vector per text and both implementations
    # are tested for it. Checked again here because the cost of being
    # wrong is silent, permanent and invisible in every log.
    provider = Recorder(vectors=[[1.0, 1.0]])

    with pytest.raises(EmbeddingError, match="cannot be matched up"):
        embed_document_sections(
            [section(1), section(2, position=1)], provider=provider, collection=collection
        )

    assert collection.count() == 0


def test_a_failing_provider_writes_nothing(collection):
    with pytest.raises(EmbeddingError):
        embed_document_sections([section(1)], provider=Broken(), collection=collection)

    assert collection.count() == 0


def test_without_a_provider_it_uses_the_configured_one(collection):
    settings = Settings(embedding_provider="mock", embedding_dimensions=8)

    embed_document_sections([section(1)], collection=collection, settings=settings)

    assert len(collection.vector_for("1")) == 8


# --- the question half -------------------------------------------------


def test_a_question_is_embedded_to_a_single_vector():
    provider = Recorder(vectors=[[0.1, 0.2]])

    assert embed_question("How much leave do I get?", provider=provider) == [0.1, 0.2]
    assert provider.asked == [["How much leave do I get?"]]


def test_a_question_uses_the_same_provider_as_the_sections():
    # A question embedded by a different model than the sections is a
    # question whose distances mean nothing, and the symptom is not an
    # error - it is retrieval that returns plausible rubbish.
    settings = Settings(embedding_provider="mock", embedding_dimensions=8)

    assert len(embed_question("anything", settings=settings)) == 8


def test_a_provider_answering_a_question_with_two_vectors_is_refused():
    provider = Recorder(vectors=[[0.1], [0.2]])

    with pytest.raises(EmbeddingError, match="for one question"):
        embed_question("anything", provider=provider)
