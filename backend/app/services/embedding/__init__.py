"""The Embedding Client and the Embedding API behind it (ON-41).

Two of the components the architecture diagram names:

* **Embedding Client** - `client.py`. Calls the Embedding API for each
  section of an uploaded document and stores the vectors in the Vector
  Database (U4), and embeds employee questions for retrieval (step 2).
* **Embedding API** - an external system, reached by `hosted.py` over
  HTTPS. ON-10 chose it: OpenAI `text-embedding-3-small`, 1536 dimensions,
  with the key on the server only.

`mock.py` is the stand-in for CI and for teammates with no key, selected by
`EMBEDDING_PROVIDER=mock` and never by accident - the same arrangement
CLAUDE.md requires for the Mock LLM, for the same reason.

Nothing above this package learns which provider it got. The Documents API
asks for its sections to be embedded; the Retrieval Service (ON-43) asks
for a question to be embedded; neither mentions a provider, a model or a
vector width.
"""

from app.services.embedding.client import (
    embed_document_sections,
    embed_question,
    text_for_embedding,
)
from app.services.embedding.hosted import HostedEmbeddingClient
from app.services.embedding.mock import MockEmbedder
from app.services.embedding.provider import EmbeddingError, EmbeddingProvider
from app.services.embedding.selection import PROVIDERS, get_provider
from app.services.embedding.store import forget_document, remember_sections

__all__ = [
    "PROVIDERS",
    "EmbeddingError",
    "EmbeddingProvider",
    "HostedEmbeddingClient",
    "MockEmbedder",
    "embed_document_sections",
    "embed_question",
    "forget_document",
    "get_provider",
    "remember_sections",
    "text_for_embedding",
]
