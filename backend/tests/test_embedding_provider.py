"""The EmbeddingProvider interface (ON-41)."""

import pytest

from app.services.embedding import HostedEmbeddingClient, MockEmbedder
from app.services.embedding.provider import EmbeddingError, EmbeddingProvider


def test_a_provider_without_embed_cannot_be_built():
    # An abstract base class rather than a Protocol, so forgetting the one
    # method fails when somebody builds the class rather than later, when
    # something asks it for a vector.
    class Forgetful(EmbeddingProvider):
        pass

    with pytest.raises(TypeError):
        Forgetful()


def test_the_interface_has_exactly_one_abstract_method():
    # Every extra argument or method here is a reason the callers have to
    # change when the provider does, which is the thing it exists to stop.
    assert EmbeddingProvider.__abstractmethods__ == frozenset({"embed"})


@pytest.mark.parametrize("provider", [HostedEmbeddingClient, MockEmbedder])
def test_both_providers_implement_the_interface(provider):
    assert issubclass(provider, EmbeddingProvider)


def test_a_provider_names_itself_for_the_log():
    assert MockEmbedder().name == "MockEmbedder"


def test_every_failure_is_one_type_a_caller_can_catch():
    # One type for no key, a refusal, a timeout, an unreachable host and a
    # reply that made no sense, so a caller has one thing to catch rather
    # than a list that grows with every provider.
    assert issubclass(EmbeddingError, Exception)
