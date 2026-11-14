"""Choosing an embedding provider (ON-41).

The same shape as `test_llm_provider.py`, and for the same reason: the
dangerous outcome is not a crash, it is a deployment that believes it is
embedding against the Embedding API while quietly using the mock.
"""

import logging

import pytest

from app.config import Settings
from app.services.embedding import HostedEmbeddingClient, MockEmbedder
from app.services.embedding.selection import PROVIDERS, get_provider


def settings_for(name: str) -> Settings:
    return Settings(embedding_provider=name, embedding_api_key="sk-test")


def test_openai_selects_the_hosted_client():
    assert isinstance(get_provider(settings_for("openai")), HostedEmbeddingClient)


def test_mock_selects_the_mock_embedder():
    assert isinstance(get_provider(settings_for("mock")), MockEmbedder)


def test_the_table_holds_exactly_the_two_providers_that_exist():
    assert sorted(PROVIDERS) == ["mock", "openai"]


@pytest.mark.parametrize("name", ["OpenAI", "  openai  ", "MOCK"])
def test_the_name_is_not_case_or_whitespace_sensitive(name):
    assert get_provider(settings_for(name)) is not None


def test_an_unknown_name_is_an_error_and_not_a_quiet_fall_back():
    # Falling back to the mock would mean a deployment that answers from
    # lexical vectors and says so nowhere anybody is looking.
    with pytest.raises(RuntimeError) as refused:
        get_provider(settings_for("cohere"))

    message = str(refused.value)
    assert "'cohere'" in message
    assert "mock" in message and "openai" in message


def test_the_hosted_provider_is_the_default():
    # ON-10 chose hosted OpenAI. The mock has to be asked for by name; a
    # default of "mock" would make every machine without a key look like it
    # was working.
    assert Settings().embedding_provider == "openai"


def test_selecting_the_mock_says_so_loudly(caplog):
    with caplog.at_level(logging.WARNING):
        get_provider(settings_for("mock"))

    assert any(record.levelno >= logging.WARNING for record in caplog.records)
    assert "not the Embedding API" in caplog.text


def test_selecting_the_hosted_provider_does_not_warn(caplog):
    with caplog.at_level(logging.WARNING):
        get_provider(settings_for("openai"))

    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


def test_the_chosen_provider_is_given_the_settings_it_was_chosen_from():
    # Otherwise it would build its own from the environment and could
    # disagree with the caller about the model or the vector width.
    settings = Settings(embedding_provider="mock", embedding_dimensions=8)

    assert len(get_provider(settings).embed(["hello"])[0]) == 8
