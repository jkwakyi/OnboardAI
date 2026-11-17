"""Faults for POST /api/chat/ask and the Logging Service (ON-47).

The endpoint has two promises and they pull in opposite directions, which
is what makes the faults interesting.

The first is that **the AI path never produces an error status**: a
timeout, a provider error, invalid output, no good match and an Embedding
API that is down all come back 200 with `fallback: true`. The second is
that **every answer is saved and the id returned is real**, because the
Chat Page rates answers and escalates fallbacks by that id. Several
faults here turn one promise into the other - an AI failure becoming a
500, or a database failure becoming a cheerful 200 with an id pointing at
nothing.

Four are changes somebody would make deliberately:

* "a fallback is not worth saving" halves the table and looks like
  avoiding noise. It is also the only record ON-24 counts the fallback
  rate from, so the number it reports would be zero and look excellent.
* "a question longer than the Gateway will read is accepted" removes a
  limit that looks arbitrary. The Gateway truncates, so the employee gets
  a confident answer to the first two thousand characters of their
  question with nothing to say the rest was dropped.
* "the chat is saved after the response is built" looks like getting the
  answer out faster. The id in the response then belongs to a row that
  may never be written.
* "a database failure returns the fallback like everything else" looks
  consistent with the contracts' rule about never showing an error. It
  hands back `id: 0`, and the Chat Page's "Send to HR" then fails against
  a foreign key in front of the employee.
"""

TESTS = [
    "tests/test_chat_api.py",
    "tests/test_chat_logs.py",
    "tests/test_auth_check.py",
    "tests/test_qa_controller.py",
]

API = "app/api/chat.py"
LOGS = "app/services/logs/chat.py"
PACKAGE = "app/services/logs/__init__.py"

# Two faults were written and then removed as proving nothing:
#
# * "a question of no characters at all is accepted" moved `min_length=1`
#   to 0, which changed no behaviour because the `_must_say_something`
#   validator already refuses an empty string. The redundancy was the
#   real finding, and `min_length` is gone from the endpoint; the
#   validator is what the blank-question faults target now.
# * "the question is attributed to whoever asked last" was a duplicate of
#   the `user_id` fault below, written badly enough to collapse to the
#   same constant.

FAULTS = [
    # --- the AI path never produces an error status --------------------
    (
        "a fallback is turned into an error for the employee",
        API,
        "    return AskResponse(\n        id=chat_log.id,",
        "    if answer.fallback:\n        raise HTTPException(status_code=503, detail=answer.answer)\n    return AskResponse(\n        id=chat_log.id,",
    ),
    (
        "the fallback flag is not passed on, so the Chat Page cannot offer HR",
        API,
        "        fallback=answer.fallback,\n    )",
        "        fallback=False,\n    )",
    ),
    (
        "the employee is shown why the answer failed",
        API,
        "        answer=answer.answer,\n        citations=",
        "        answer=f'{answer.answer} ({answer.reason})',\n        citations=",
    ),
    # --- step 9: every answer is saved ----------------------------------
    (
        # The quiet one. Answers still work; the fallback rate reads zero.
        "a fallback is not worth saving",
        API,
        "    try:\n        chat_log = save_chat(",
        "    if answer.fallback:\n        return AskResponse(id=0, answer=answer.answer, citations=[], fallback=True)\n    try:\n        chat_log = save_chat(",
    ),
    (
        "the chat is never written at all",
        API,
        "        chat_log = save_chat(\n            session,",
        "        chat_log = ChatLog(id=0)\n        _unused = save_chat and (\n            session,",
    ),
    (
        "the saved question is the raw one rather than what was asked",
        API,
        "            question=question,\n            answer=answer.answer,",
        '            question="",\n            answer=answer.answer,',
    ),
    (
        "the saved answer is not the one the employee read",
        LOGS,
        "        answer=answer,",
        '        answer="",',
    ),
    (
        "a fallback is saved as though it were an answer",
        LOGS,
        "        fallback=fallback,",
        "        fallback=False,",
    ),
    (
        # Missed on the first pass: the only test that read `user_id`
        # used the employee, who is user 1, so the hard-coded value and
        # the correct one were the same number. There is now a test that
        # asks as the HR administrator.
        "the chat is recorded against the wrong person",
        LOGS,
        "        user_id=user_id,",
        "        user_id=1,",
    ),
    (
        "the write is never flushed, so the row has no id yet",
        LOGS,
        "    session.add(chat_log)\n    session.flush()",
        "    session.add(chat_log)",
    ),
    (
        "the Logging Service commits the caller's transaction for it",
        LOGS,
        "    session.add(chat_log)\n    session.flush()",
        "    session.add(chat_log)\n    session.commit()",
    ),
    (
        "the endpoint never commits, so nothing survives the request",
        API,
        "        session.commit()\n    except SQLAlchemyError:",
        "        pass\n    except SQLAlchemyError:",
    ),
    # --- the id that comes back ------------------------------------------
    (
        "the response carries an id that is not the saved row's",
        API,
        "        id=chat_log.id,",
        "        id=1,",
    ),
    (
        "a database failure comes back as a cheerful answer with no row behind it",
        API,
        '        raise HTTPException(\n            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,\n            detail="The answer could not be recorded. Please try again.",\n        ) from None',
        "        return AskResponse(id=0, answer=answer.answer, citations=[], fallback=True)",
    ),
    (
        "a failed write leaves its half-written row behind",
        API,
        "        session.rollback()\n        logger.exception",
        "        logger.exception",
    ),
    # --- the citations ----------------------------------------------------
    (
        "the citations never reach the Chat Page",
        API,
        "        citations=[CitationResponse(**row) for row in citation_rows(answer.citations)],",
        "        citations=[],",
    ),
    (
        "a citation loses the id that makes it followable",
        LOGS,
        '            "section_id": citation.section_id,',
        '            "section_id": 0,',
    ),
    (
        "a citation loses the document it came from",
        LOGS,
        '            "document": citation.document,',
        '            "document": None,',
    ),
    (
        "a citation loses its heading",
        LOGS,
        '            "heading": citation.heading,',
        '            "heading": None,',
    ),
    (
        "the order the model used its citations in is lost",
        LOGS,
        "    return [\n        {\n            \"section_id\": citation.section_id,",
        "    citations = sorted(citations, key=lambda c: c.section_id)\n    return [\n        {\n            \"section_id\": citation.section_id,",
    ),
    (
        # Spelled out by hand for exactly this reason.
        "every field of a Citation is written out, whatever gets added to it",
        LOGS,
        '    return [\n        {\n            "section_id": citation.section_id,\n            "heading": citation.heading,\n            "document": citation.document,\n        }\n        for citation in citations\n    ]',
        "    from dataclasses import asdict\n\n    return [asdict(citation) for citation in citations]",
    ),
    (
        "no citations becomes null rather than an empty list",
        LOGS,
        "    return [\n        {\n            \"section_id\": citation.section_id,",
        "    if not citations:\n        return None\n    return [\n        {\n            \"section_id\": citation.section_id,",
    ),
    # --- what is still an error --------------------------------------------
    (
        "a blank question is sent on to be answered",
        API,
        "        if not value.strip():\n            raise ValueError",
        "        if False:\n            raise ValueError",
    ),
    (
        "a question longer than the Gateway will read is accepted",
        API,
        "        max_length=MAX_QUESTION_CHARACTERS,",
        "        max_length=100_000,",
    ),
    (
        "the limit is a number of this endpoint's own, free to drift",
        API,
        "        max_length=MAX_QUESTION_CHARACTERS,",
        "        max_length=1000,",
    ),
    (
        "a token naming an account that is gone is allowed through",
        API,
        "    if asker is None:",
        "    if False:",
    ),
    # --- what the package offers ----------------------------------------------
    (
        "the Logging Service stops exporting what the Chat API imports",
        PACKAGE,
        '__all__ = ["citation_rows", "save_chat"]',
        '__all__ = ["save_chat"]\ndel citation_rows',
    ),
]
