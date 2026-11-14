"""The Real Embedding Client (ON-41).

Every test here injects the transport, so the suite needs no key, costs
nothing and passes offline. What it is actually checking is that a
provider behaving badly - reordering its answers, returning a short list,
changing the vector width, echoing the key back inside an error - is
caught here rather than written into the Vector Database.
"""

import io
import json
import urllib.error
import urllib.request

import pytest

from app.config import Settings
from app.services.embedding.hosted import (
    HostedEmbeddingClient,
    batched,
    read_embeddings,
    redact,
)
from app.services.embedding.provider import EmbeddingError

KEY = "sk-test-not-a-real-key"


def settings_for(**overrides) -> Settings:
    base = {
        "embedding_provider": "openai",
        "embedding_api_url": "https://embeddings.test/v1/embeddings",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 3,
        "embedding_batch_size": 64,
        "embedding_timeout_seconds": 9.5,
        "embedding_api_key": KEY,
    }
    base.update(overrides)
    return Settings(**base)


class Recorder:
    """A transport that records what it was given and replies as told."""

    def __init__(self, replies=None, width=3):
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []
        self.replies = replies
        self.width = width

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.replies is not None:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        count = len(json.loads(request.data)["input"])
        return payload([[float(index)] * self.width for index in range(count)])

    @property
    def bodies(self) -> list[dict]:
        return [json.loads(request.data) for request in self.requests]


def payload(vectors, indices=None) -> bytes:
    """A provider reply carrying `vectors`."""
    if indices is None:
        indices = range(len(vectors))
    data = [
        {"index": index, "embedding": vector}
        for index, vector in zip(indices, vectors, strict=True)
    ]
    return json.dumps({"data": data, "model": "text-embedding-3-small"}).encode("utf-8")


def http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://embeddings.test/v1/embeddings", code, "refused", {}, io.BytesIO(body.encode())
    )


def client_with(transport, **overrides) -> HostedEmbeddingClient:
    return HostedEmbeddingClient(settings_for(**overrides), send=transport)


# --- the request -------------------------------------------------------


def test_it_posts_to_the_configured_endpoint():
    sent = Recorder()
    client_with(sent).embed(["hello"])

    assert sent.requests[0].full_url == "https://embeddings.test/v1/embeddings"
    assert sent.requests[0].method == "POST"


def test_it_sends_the_texts_and_the_configured_model():
    sent = Recorder()
    client_with(sent).embed(["one", "two"])

    assert sent.bodies[0] == {"input": ["one", "two"], "model": "text-embedding-3-small"}


def test_it_sends_the_key_as_a_bearer_token():
    sent = Recorder()
    client_with(sent).embed(["hello"])

    assert sent.requests[0].get_header("Authorization") == f"Bearer {KEY}"


def test_it_applies_the_configured_timeout():
    sent = Recorder()
    client_with(sent).embed(["hello"])

    assert sent.timeouts == [9.5]


def test_no_texts_means_no_request_at_all():
    sent = Recorder()

    assert client_with(sent).embed([]) == []
    assert sent.requests == []


def test_a_missing_key_is_refused_before_anything_is_sent():
    sent = Recorder()
    client = client_with(sent, embedding_api_key=None)

    with pytest.raises(EmbeddingError) as refused:
        client.embed(["hello"])

    # The message from `require_embedding_api_key`, which says where to put
    # it - passed through rather than replaced with something vaguer.
    assert "EMBEDDING_API_KEY is not set" in str(refused.value)
    assert ".env" in str(refused.value)
    assert sent.requests == []


# --- batching ----------------------------------------------------------


def test_it_sends_several_batches_rather_than_one_huge_request():
    sent = Recorder()
    client_with(sent, embedding_batch_size=2).embed(["a", "b", "c", "d", "e"])

    assert [len(body["input"]) for body in sent.bodies] == [2, 2, 1]


def test_a_batched_answer_comes_back_in_the_original_order():
    # Each batch's vectors are numbered from zero inside that batch, so a
    # client that merely concatenated them would still look right. These
    # are distinguishable: the text is what it embeds to.
    sent = Recorder(
        replies=[
            payload([[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]),
            payload([[3.0, 3.0, 3.0], [4.0, 4.0, 4.0]]),
            payload([[5.0, 5.0, 5.0]]),
        ]
    )

    vectors = client_with(sent, embedding_batch_size=2).embed(["a", "b", "c", "d", "e"])

    assert [vector[0] for vector in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_one_failed_batch_fails_the_whole_call():
    # Rather than returning the batches that worked, which would be a
    # short list silently matched against the wrong sections.
    sent = Recorder(replies=[payload([[1.0, 1.0, 1.0]]), http_error(500, "boom")])
    client = client_with(sent, embedding_batch_size=1)

    with pytest.raises(EmbeddingError):
        client.embed(["a", "b"])


def test_batched_refuses_a_size_of_zero():
    with pytest.raises(ValueError):
        list(batched(["a"], 0))


# --- putting the answers back in order ---------------------------------


def test_answers_are_ordered_by_the_index_the_provider_reported():
    # The endpoint does not promise array order. This is the single most
    # consequential thing in the file: a vector attached to the wrong
    # section produces confident citations of the wrong paragraph, and
    # nothing anywhere would report an error.
    out_of_order = payload([[9.0, 9.0, 9.0], [1.0, 1.0, 1.0]], indices=[1, 0])
    sent = Recorder(replies=[out_of_order])

    vectors = client_with(sent).embed(["first", "second"])

    assert vectors == [[1.0, 1.0, 1.0], [9.0, 9.0, 9.0]]


def test_read_embeddings_refuses_a_duplicated_index():
    duplicated = {
        "data": [
            {"index": 0, "embedding": [1.0]},
            {"index": 0, "embedding": [2.0]},
        ]
    }
    with pytest.raises(EmbeddingError, match="twice"):
        read_embeddings(duplicated, expected=2)


def test_read_embeddings_refuses_an_index_nobody_asked_for():
    with pytest.raises(EmbeddingError, match="not asked for"):
        read_embeddings({"data": [{"index": 7, "embedding": [1.0]}]}, expected=1)


def test_read_embeddings_refuses_a_non_integer_index():
    with pytest.raises(EmbeddingError, match="integer 'index'"):
        read_embeddings({"data": [{"index": "0", "embedding": [1.0]}]}, expected=1)


# --- a reply that makes no sense ---------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ([], "not a JSON object"),
        ({}, "no 'data' array"),
        ({"data": "nope"}, "no 'data' array"),
        ({"data": [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [1.0]}]}, "got 2"),
        ({"data": ["nope"]}, "not an object"),
        ({"data": [{"index": 0}]}, "missing or empty"),
        ({"data": [{"index": 0, "embedding": []}]}, "missing or empty"),
        ({"data": [{"index": 0, "embedding": "nope"}]}, "missing or empty"),
        ({"data": [{"index": 0, "embedding": ["1.0"]}]}, "not a number"),
    ],
)
def test_read_embeddings_refuses_a_malformed_shape(body, expected):
    with pytest.raises(EmbeddingError, match=expected):
        read_embeddings(body, expected=1)


def test_a_vector_of_booleans_is_not_a_vector_of_numbers():
    # `isinstance(True, int)` is True in Python, so a naive number check
    # would accept this and store a vector of ones and zeros.
    with pytest.raises(EmbeddingError, match="not a number"):
        read_embeddings({"data": [{"index": 0, "embedding": [True, False]}]}, expected=1)


def test_a_reply_that_is_not_json_is_refused():
    sent = Recorder(replies=[b"<html>Bad Gateway</html>"])
    client = client_with(sent)

    with pytest.raises(EmbeddingError, match="not JSON"):
        client.embed(["hello"])


# --- the width has to match --------------------------------------------


def test_a_different_vector_width_is_refused():
    sent = Recorder(replies=[payload([[1.0] * 768])])
    client = client_with(sent)

    with pytest.raises(EmbeddingError) as refused:
        client.embed(["hello"])

    message = str(refused.value)
    assert "768" in message
    assert "EMBEDDING_DIMENSIONS is 3" in message
    # The actionable half: the width follows from the model.
    assert "EMBEDDING_MODEL" in message


def test_the_configured_width_is_accepted():
    sent = Recorder(replies=[payload([[0.1, 0.2, 0.3]])])

    assert client_with(sent).embed(["hello"]) == [[0.1, 0.2, 0.3]]


# --- refusals, outages and timeouts ------------------------------------


def test_a_401_says_the_key_may_be_wrong():
    sent = Recorder(replies=[http_error(401, '{"error": "invalid_api_key"}')])
    client = client_with(sent)

    with pytest.raises(EmbeddingError, match="may be wrong or revoked"):
        client.embed(["hello"])


def test_a_429_says_the_account_may_be_out_of_credit():
    # The real failure on this project's first live attempt: the key was
    # valid and the account was empty. A bare "429" sends somebody looking
    # at the wrong thing.
    sent = Recorder(replies=[http_error(429, '{"error": "insufficient_quota"}')])
    client = client_with(sent)

    with pytest.raises(EmbeddingError, match="out of credit"):
        client.embed(["hello"])


def test_a_refusal_carries_the_providers_own_words():
    sent = Recorder(replies=[http_error(400, '{"error": "input is too long"}')])
    client = client_with(sent)

    with pytest.raises(EmbeddingError, match="input is too long"):
        client.embed(["hello"])


def test_the_key_never_appears_in_an_error():
    # Providers echo the request back in error payloads.
    sent = Recorder(replies=[http_error(400, f'{{"error": "bad request with {KEY}"}}')])
    client = client_with(sent)

    with pytest.raises(EmbeddingError) as refused:
        client.embed(["hello"])

    assert KEY not in str(refused.value)
    assert "***" in str(refused.value)


def test_an_unreachable_provider_is_reported_as_unreachable():
    sent = Recorder(replies=[urllib.error.URLError("no route to host")])
    client = client_with(sent)

    with pytest.raises(EmbeddingError, match="could not reach"):
        client.embed(["hello"])


def test_a_timeout_names_the_limit_it_passed():
    sent = Recorder(replies=[TimeoutError()])
    client = client_with(sent)

    with pytest.raises(EmbeddingError, match="within 9.5 seconds"):
        client.embed(["hello"])


# --- redaction ---------------------------------------------------------


def test_redact_removes_the_secret():
    assert redact(f"sent {KEY} along", KEY) == "sent *** along"


def test_redact_leaves_text_alone_when_there_is_no_secret():
    assert redact("nothing to hide", "") == "nothing to hide"
