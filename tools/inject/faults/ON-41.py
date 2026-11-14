"""Faults for the Embedding Client (ON-41).

This component has a failure mode the rest of the system does not: it can
be wrong without anything going wrong. A vector attached to the wrong
section raises nothing, logs nothing, and produces an assistant that cites
the wrong paragraph with complete confidence. So a good half of these
faults are reorderings and off-by-ones rather than outright breakage, and
the question each asks is whether a test would notice the system quietly
becoming untrustworthy.

Four are changes somebody would make on purpose, each for a reason a
reviewer would accept:

* "the answers are taken in the order they arrived" is what you write if
  you have not read the part of the provider's documentation that says the
  order is not promised. It passes every test that uses a provider which
  happens to answer in order - which is every provider, almost always.
* "the heading is left out of what gets embedded" looks like removing a
  duplication, since the heading is stored in the metadata already.
* "the mock becomes the fall back for an unknown provider" looks like
  robustness. It means a typo in `EMBEDDING_PROVIDER` produces a system
  that runs, answers, and is quietly embedding with the wrong thing.
* "a failed upload keeps its vectors" looks like leaving the Vector
  Database alone on an error path. It leaves rows retrieval will find and
  then be unable to read.
"""

TESTS = [
    "tests/test_embedding_hosted.py",
    "tests/test_embedding_mock.py",
    "tests/test_embedding_client.py",
    "tests/test_embedding_store.py",
    "tests/test_embedding_selection.py",
    "tests/test_embedding_provider.py",
    "tests/test_vectorstore.py",
    "tests/test_documents_api.py",
]

HOSTED = "app/services/embedding/hosted.py"
MOCK = "app/services/embedding/mock.py"
CLIENT = "app/services/embedding/client.py"
STORE = "app/services/embedding/store.py"
SELECTION = "app/services/embedding/selection.py"
CHROMA = "app/vectorstore/chroma.py"
CONFIG = "app/config.py"
API = "app/api/documents.py"

FAULTS = [
    # --- the request ---------------------------------------------------
    (
        "the key is not sent",
        HOSTED,
        '                "Authorization": f"Bearer {key}",',
        '                "Accept-Encoding": "identity",',
    ),
    (
        "the configured model is ignored",
        HOSTED,
        '        body = json.dumps({"input": texts, "model": self._settings.embedding_model}).encode(',
        '        body = json.dumps({"input": texts, "model": "text-embedding-ada-002"}).encode(',
    ),
    (
        "only the first text of a batch is sent",
        HOSTED,
        '        body = json.dumps({"input": texts, "model": self._settings.embedding_model}).encode(',
        '        body = json.dumps({"input": texts[:1], "model": self._settings.embedding_model}).encode(',
    ),
    (
        "the timeout is not applied",
        HOSTED,
        "            raw = self._send(request, self._settings.embedding_timeout_seconds)",
        "            raw = self._send(request, 600.0)",
    ),
    (
        "a missing key is discovered only once a request has been sent",
        HOSTED,
        "            raise EmbeddingError(str(exc)) from None",
        '            raise EmbeddingError("no key") from None',
    ),
    # --- batching ------------------------------------------------------
    (
        "everything is sent in one request however long the document",
        HOSTED,
        "        for chunk in batched(texts, settings.embedding_batch_size):",
        "        for chunk in batched(texts, 100_000):",
    ),
    (
        "a batch boundary drops a section",
        HOSTED,
        "        yield texts[start : start + size]",
        "        yield texts[start : start + size - 1] or texts[start : start + size]",
    ),
    (
        "batches overlap, so a section is embedded twice and one is lost",
        HOSTED,
        "    for start in range(0, len(texts), size):",
        "    for start in range(0, len(texts), max(1, size - 1)):",
    ),
    # --- the order of the answers --------------------------------------
    (
        # The quiet one. Nothing raises; every citation moves one section.
        "the answers are taken in the order they arrived",
        HOSTED,
        "    return [byindex[index] for index in range(expected)]",
        "    return list(byindex.values())",
    ),
    (
        "a duplicated index is accepted, leaving one section unembedded",
        HOSTED,
        '            raise EmbeddingError(f"\'data\' holds index {index} twice")',
        "            pass",
    ),
    (
        "a short answer is accepted and matched against the wrong sections",
        HOSTED,
        "    if len(data) != expected:",
        "    if False:",
    ),
    # --- validating what came back -------------------------------------
    (
        "the vector width is never checked",
        HOSTED,
        "            if len(vector) != expected:",
        "            if False:",
    ),
    (
        "booleans count as numbers, so a vector of ones and zeros is stored",
        HOSTED,
        "    return isinstance(value, (int, float)) and not isinstance(value, bool)",
        "    return isinstance(value, (int, float))",
    ),
    (
        "an empty vector is accepted",
        HOSTED,
        "        if not isinstance(vector, list) or not vector:",
        "        if not isinstance(vector, list):",
    ),
    (
        "a reply that is not JSON becomes a crash rather than a refusal",
        HOSTED,
        "        except (UnicodeDecodeError, json.JSONDecodeError) as exc:",
        "        except (UnicodeDecodeError, TypeError) as exc:",
    ),
    # --- failures ------------------------------------------------------
    (
        "a refusal loses the provider's own explanation",
        HOSTED,
        '        message = f"the Embedding API answered {exc.code}.{hints.get(exc.code, \'\')} {detail}"',
        '        message = f"the Embedding API answered {exc.code}."',
    ),
    (
        "the key is left in the error the provider echoed it into",
        HOSTED,
        "    return text.replace(secret, \"***\")",
        "    return text",
    ),
    (
        "a 429 is not explained, so an empty account looks like a rate limit",
        HOSTED,
        '            429: " The account may be out of credit, or the rate limit was hit.",',
        '            429: "",',
    ),
    (
        "an unreachable provider is reported as a timeout",
        HOSTED,
        '            raise EmbeddingError(f"could not reach the Embedding API: {exc.reason}") from None',
        '            raise EmbeddingError("the Embedding API did not answer within 0 seconds") from None',
    ),
    # --- the mock ------------------------------------------------------
    (
        # Passes everything except the cross-process golden vectors.
        "the mock uses Python's salted hash, so vectors change every run",
        MOCK,
        '            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()',
        '            digest = abs(hash(token)).to_bytes(8, "big", signed=False)[:8]',
    ),
    (
        "the mock does not scale to unit length, so cosine is meaningless",
        MOCK,
        "        return [value / length for value in vector]",
        "        return vector",
    ),
    (
        "a text with no words gets a vector of zeros, which has no direction",
        MOCK,
        "            unit = [0.0] * width\n            unit[0] = 1.0\n            return unit",
        "            return vector",
    ),
    (
        "the mock ignores the configured width",
        MOCK,
        "        width = self._settings.embedding_dimensions",
        "        width = 384",
    ),
    (
        "tokenising drops digits, so 30 days and 90 days are the same text",
        MOCK,
        'WORD = re.compile(r"[a-z0-9]+")',
        'WORD = re.compile(r"[a-z]+")',
    ),
    # --- what gets embedded --------------------------------------------
    (
        "the heading is left out of what gets embedded",
        CLIENT,
        '        return f"{section.heading}\\n\\n{section.text}"',
        "        return section.text",
    ),
    (
        "a provider returning the wrong number of vectors is not caught",
        CLIENT,
        "    if len(vectors) != len(sections):",
        "    if False:",
    ),
    (
        "a question is embedded by a provider of its own",
        CLIENT,
        "    chosen = provider if provider is not None else get_provider(settings)\n    vectors = chosen.embed([question])",
        "    from app.services.embedding.mock import MockEmbedder\n\n    chosen = MockEmbedder()\n    vectors = chosen.embed([question])",
    ),
    # --- storing -------------------------------------------------------
    (
        "a vector is keyed by its position rather than its section id",
        STORE,
        "            ids=[str(section.id) for section in chunk],",
        "            ids=[str(section.position) for section in chunk],",
    ),
    (
        "the metadata does not say which document a section came from",
        STORE,
        '        "document_id": section.document_id,',
        '        "document_id": 0,',
    ),
    (
        "a missing heading is stored as null, which ChromaDB cannot hold",
        STORE,
        '        "heading": section.heading or "",',
        '        "heading": section.heading,',
    ),
    (
        "sections and vectors are no longer counted against each other",
        STORE,
        "    if len(sections) != len(vectors):",
        "    if False:",
    ),
    (
        "a long document is written in one call and exceeds ChromaDB's limit",
        STORE,
        "MAX_WRITE_BATCH = 500",
        "MAX_WRITE_BATCH = 100_000",
    ),
    (
        "a re-run fails on a duplicate id instead of replacing the vector",
        STORE,
        "        target.upsert(",
        "        target.add(",
    ),
    (
        "forgetting a document removes every vector in the collection",
        STORE,
        '    target.delete(where={"document_id": document_id})',
        "    target.delete(where={})",
    ),
    # --- choosing a provider -------------------------------------------
    (
        "the mock becomes the fall back for an unknown provider",
        SELECTION,
        "        raise RuntimeError(",
        "        return MockEmbedder(settings)\n        raise RuntimeError(",
    ),
    (
        "the mock is selected silently",
        SELECTION,
        "        logger.warning(",
        "        logger.debug(",
    ),
    (
        "the mock becomes the default",
        CONFIG,
        '    embedding_provider: str = "openai"',
        '    embedding_provider: str = "mock"',
    ),
    (
        "the provider builds its own settings rather than being given them",
        SELECTION,
        "    return provider(settings)",
        "    return provider()",
    ),
    # --- the collection ------------------------------------------------
    (
        "ChromaDB is left to embed things itself with a model of its own",
        CHROMA,
        "        name=settings.chroma_collection, embedding_function=None",
        "        name=settings.chroma_collection",
    ),
    # --- the endpoint --------------------------------------------------
    (
        "an upload that could not be embedded answers 201 anyway",
        API,
        "        embedded = embed_document_sections(sections)",
        "        embedded = 0\n        try:\n            embedded = embed_document_sections(sections)\n        except Exception:\n            pass",
    ),
    (
        "a failed upload keeps its vectors",
        API,
        "            forget_document(document_id)",
        "            pass",
    ),
    (
        "the refusal repeats the internal error to the browser",
        API,
        '            detail="The document could not be prepared for search. Please try again.",',
        "            detail=str(sections),",
    ),
]
