"""Faults for the Retrieval Service (ON-43).

Retrieval is the component with the least to crash and the most to get
quietly wrong. A broken ranking still returns five real sections with real
text and real citations; a broken score still returns a number the
threshold in ON-46 will compare against. Nothing raises, nothing is
logged, and the employee reads a confident answer assembled out of the
wrong paragraphs. So most of these faults produce a system that works.

Five are changes somebody would make on purpose:

* "the rows are used in the order the database returned them" is what you
  write when you have not noticed that `WHERE id IN (...)` has no order.
  It looks like a simplification - the dictionary lookup does appear
  redundant - and on a small table the planner often returns rows in a
  plausible-looking order anyway.
* "the relevance score is clamped at zero" looks like tidying up a number
  that should obviously never be negative. It tells ON-46 that a section
  pointing the opposite way is merely unhelpful rather than actively
  wrong.
* "a section the Main Database has lost is kept" looks like robustness:
  do not drop a result just because one lookup missed. It produces a
  citation to a section that does not exist.
* "the collection is left in ChromaDB's default space" is a one-line
  simplification that ranks identically and scores wrongly.
* "a blank question is embedded like any other" removes a special case.
  It spends a request to retrieve the five sections nearest the origin of
  the vector space and presents them as matches.
"""

TESTS = [
    "tests/test_retrieval.py",
    "tests/test_vectorstore.py",
    "tests/test_embedding_store.py",
    "tests/test_migrations.py",
]

SERVICE = "app/services/retrieval/service.py"
PACKAGE = "app/services/retrieval/__init__.py"
CHROMA = "app/vectorstore/chroma.py"
ENV = "migrations/env.py"

FAULTS = [
    # --- the ranking, which nothing downstream can check ----------------
    (
        # The quiet one. Every result is a real section, every citation
        # resolves, and the order is whatever the planner felt like.
        "the rows are used in the order the database returned them",
        SERVICE,
        "    results: list[RetrievedSection] = []\n    missing: list[int] = []\n    for section_id, distance in ranked:",
        "    results: list[RetrievedSection] = []\n    missing: list[int] = []\n    for section_id, distance in sorted(ranked):",
    ),
    (
        "the ranking is reversed, so the worst match is cited first",
        SERVICE,
        "    ranked = _ranked_ids(answer)",
        "    ranked = list(reversed(_ranked_ids(answer)))",
    ),
    (
        "each result is given the distance of the one after it",
        SERVICE,
        "    for identifier, distance in zip(id_lists[0], distances, strict=True):",
        "    for identifier, distance in zip(id_lists[0], distances[1:] + distances[:1], strict=True):",
    ),
    # --- the score ------------------------------------------------------
    (
        "relevance is read straight off the distance, so near becomes far",
        SERVICE,
        "    return 1.0 - distance",
        "    return distance",
    ),
    (
        "the relevance score is clamped at zero",
        SERVICE,
        "    return 1.0 - distance",
        "    return max(0.0, 1.0 - distance)",
    ),
    (
        "the raw distance is not reported beside the score",
        SERVICE,
        "                distance=distance,",
        "                distance=0.0,",
    ),
    # --- the space those scores assume ----------------------------------
    (
        "the collection is left in ChromaDB's default space",
        CHROMA,
        '        metadata={"hnsw:space": DISTANCE_SPACE},\n',
        "",
    ),
    (
        "a collection that came back in another space is accepted anyway",
        CHROMA,
        "    space = configured_space(collection)\n    if space == DISTANCE_SPACE:\n        return collection",
        "    space = configured_space(collection)\n    if space != DISTANCE_SPACE:\n        return collection",
    ),
    (
        "a collection that will not say which space it uses is let through",
        CHROMA,
        "    space = configured_space(collection)\n    if space == DISTANCE_SPACE:",
        "    space = configured_space(collection) or DISTANCE_SPACE\n    if space == DISTANCE_SPACE:",
    ),
    (
        "the space is taken from what we asked for, not from what came back",
        CHROMA,
        "    configuration = getattr(collection, \"configuration_json\", None)",
        "    return DISTANCE_SPACE\n    configuration = getattr(collection, \"configuration_json\", None)",
    ),
    (
        # Replaces "the refusal does not say which collection is wrong",
        # which was a bad fault: it took the name out of the opening
        # clause while the remedy below still interpolated it, so the
        # operator was told exactly the same thing and no test should
        # have failed. This one has a consequence - the command in the
        # message deletes a collection other than the broken one.
        "the remedy tells the operator to delete a different collection",
        CHROMA,
        "delete_collection('{name}')",
        "delete_collection('onboardai_sections')",
    ),
    (
        "the refusal does not say how to put it right",
        CHROMA,
        '        f\'re-uploaded: python -c "import chromadb; \'@        f"chromadb.HttpClient(host=\'HOST\', port=PORT).delete_collection(\'{name}\')\\""'.replace('@', chr(10)),
        '        f"re-uploaded."',
    ),
    # --- how many ---------------------------------------------------------
    (
        "more than the five sections the contracts fix are retrieved",
        SERVICE,
        "TOP_K = 5",
        "TOP_K = 20",
    ),
    (
        "the limit is not passed to the Vector Database",
        SERVICE,
        "    answer = target.query(query_embeddings=[vector], n_results=limit, include=INCLUDE)",
        "    answer = target.query(query_embeddings=[vector], n_results=100, include=INCLUDE)",
    ),
    (
        "the section text is asked for from the Vector Database, which never had it",
        SERVICE,
        'INCLUDE = ["distances", "metadatas"]',
        'INCLUDE = ["distances", "metadatas", "documents"]',
    ),
    (
        "the distances are not asked for at all",
        SERVICE,
        'INCLUDE = ["distances", "metadatas"]',
        'INCLUDE = ["metadatas"]',
    ),
    # --- the two stores disagreeing --------------------------------------
    (
        "a section the Main Database has lost is kept",
        SERVICE,
        "        if section is None:\n            missing.append(section_id)\n            continue",
        "        if section is None:\n            missing.append(section_id)",
    ),
    (
        "the two stores drifting apart is not reported",
        SERVICE,
        "        logger.warning(\n            \"the Vector Database ranked %d section(s) with no row in the Main \"",
        "        logger.debug(\n            \"the Vector Database ranked %d section(s) with no row in the Main \"",
    ),
    (
        "an id the Vector Database cannot have written stops the whole answer",
        SERVICE,
        "        try:\n            ranked.append((int(identifier), float(distance)))\n        except (TypeError, ValueError):",
        "        if True:\n            ranked.append((int(identifier), float(distance)))\n        if False:",
    ),
    (
        "a corrupt id is skipped silently",
        SERVICE,
        "            logger.warning(\n                \"the Vector Database returned %r, which is not a section id; skipping it\",",
        "            logger.debug(\n                \"the Vector Database returned %r, which is not a section id; skipping it\",",
    ),
    # --- what a result carries -------------------------------------------
    (
        "a result is given its position where its section id belongs",
        SERVICE,
        "                section_id=section.id,",
        "                section_id=section.position,",
    ),
    (
        "the citation names the wrong document",
        SERVICE,
        "                document=section.document.filename,",
        '                document="handbook.pdf",',
    ),
    (
        "a missing heading is turned into an empty string",
        SERVICE,
        "                heading=section.heading,",
        '                heading=section.heading or "",',
    ),
    (
        "the text is replaced by the heading",
        SERVICE,
        "                text=section.text,",
        "                text=section.heading or section.text,",
    ),
    (
        "a result can be rewritten after it has been handed over",
        SERVICE,
        "@dataclass(frozen=True)\nclass RetrievedSection:",
        "@dataclass\nclass RetrievedSection:",
    ),
    # --- reading the sections ---------------------------------------------
    (
        "the document is left to load itself, one query per citation",
        SERVICE,
        "        select(Section).options(joinedload(Section.document)).where(Section.id.in_(ids))",
        "        select(Section).where(Section.id.in_(ids))",
    ),
    (
        "sections are looked up by document id rather than by their own",
        SERVICE,
        "    return {row.id: row for row in rows}",
        "    return {row.document_id: row for row in rows}",
    ),
    # --- questions that are not questions ---------------------------------
    (
        "a blank question is embedded like any other",
        SERVICE,
        "    if not question.strip():",
        "    if False:",
    ),
    (
        "whitespace counts as a question",
        SERVICE,
        "    if not question.strip():",
        "    if not question:",
    ),
    (
        "something other than the question is what gets embedded",
        SERVICE,
        "    vector = embed_question(question, provider=provider, settings=settings)",
        "    vector = embed_question(question.split()[0], provider=provider, settings=settings)",
    ),
    # --- failures ---------------------------------------------------------
    (
        # Makes an Embedding API outage look like an unhelpful question.
        "an embedding failure is turned into no matches",
        SERVICE,
        "    vector = embed_question(question, provider=provider, settings=settings)",
        "    try:\n        vector = embed_question(question, provider=provider, settings=settings)\n    except Exception:\n        return []",
    ),
    (
        "a Vector Database failure is swallowed",
        SERVICE,
        "    answer = target.query(query_embeddings=[vector], n_results=limit, include=INCLUDE)",
        "    try:\n        answer = target.query(query_embeddings=[vector], n_results=limit, include=INCLUDE)\n    except Exception:\n        answer = {}",
    ),
    # --- the service reaching its own collection ---------------------------
    (
        "the service builds a collection of its own rather than the configured one",
        SERVICE,
        "    target = collection if collection is not None else get_collection()",
        "    target = get_collection() if collection is None else collection\n    target = collection",
    ),
    # --- what the package offers ------------------------------------------
    (
        "the Retrieval Service stops exporting what the QA Controller imports",
        PACKAGE,
        '__all__ = ["TOP_K", "RetrievedSection", "relevance", "retrieve"]',
        '__all__ = ["retrieve"]\ndel RetrievedSection, relevance, TOP_K',
    ),
    # --- the logging the migration tests were switching off ----------------
    (
        # Found by this ticket: alembic's own default silences every
        # application logger for the rest of the process, so a test that
        # asserts "this does not warn" passes without the code running.
        "running a migration silences the application's loggers again",
        ENV,
        "    fileConfig(config.config_file_name, disable_existing_loggers=False)",
        "    fileConfig(config.config_file_name)",
    ),
]
