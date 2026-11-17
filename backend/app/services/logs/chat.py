"""Saving a chat to the Main Database (ON-47, step 9).

The Logging Service's first half. The contracts give it one line -
"Saves chats and feedback for manual review" - and have it "called by the
Chat API for feedback and by the QA Controller to save the chat (step
9)". Feedback is the Feedback epic; this is the chat.

Why a saved chat matters more than an audit trail
-------------------------------------------------
Three things downstream need the row, not just the record of it:

* **Escalation.** "When an employee gets a fallback answer, they can
  click Send to HR", and `Escalation.chat_log_id` points at the answer
  they clicked on, so HR sees the reply against the right message (E4).
  No row, no escalation.
* **Feedback.** `Feedback.chat_log_id` is the answer being rated, one
  verdict per person per answer.
* **ON-24's measurement.** The fallback rate is counted off this table.
  A chat that was not written is a fallback that did not happen as far
  as any report is concerned, which flatters the number in the one
  direction nobody would notice.

What is stored, and what is not
-------------------------------
The question, the answer the employee actually saw, the citations the
Gateway accepted, and whether it was a fallback. Not the retrieved
sections, not the prompt, not the score: the Main Database already holds
every section, and a prompt is reconstructible from the sections and the
question. Storing a copy of the text per question would make this table
the largest in the system within a week of real use, for a copy that can
drift from the approved one.

The `reason` is not stored either, and that is a deliberate gap recorded
as TD-31. It is the one thing that distinguishes a below-threshold
refusal from a model that timed out, and ON-24 will want it.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ChatLog
from app.services.llm.gateway import Citation

logger = logging.getLogger(__name__)


def citation_rows(citations: list[Citation]) -> list[dict[str, Any]]:
    """The citations as plain JSON, in the order the Gateway accepted them.

    Written out by hand rather than with `dataclasses.asdict`, so that a
    field added to `Citation` for some internal purpose does not silently
    start being written into every chat log and served to every browser.
    """
    return [
        {
            "section_id": citation.section_id,
            "heading": citation.heading,
            "document": citation.document,
        }
        for citation in citations
    ]


def save_chat(
    session: Session,
    user_id: int,
    question: str,
    answer: str,
    citations: list[Citation],
    fallback: bool,
) -> ChatLog:
    """Write one question and answer, and return the saved row.

    Flushes rather than commits. The caller owns the transaction: the
    endpoint that asked for this is in the middle of a request and is the
    only thing that knows whether the whole of it succeeded. Committing
    here would also mean the row's id came back from a transaction the
    caller could no longer roll back, which is the kind of thing that
    reads fine and leaves a chat log for a request that failed.
    """
    chat_log = ChatLog(
        user_id=user_id,
        question=question,
        answer=answer,
        citations=citation_rows(citations),
        fallback=fallback,
    )
    session.add(chat_log)
    session.flush()

    logger.info(
        "saved chat %s for user %s (fallback=%s, %d citation(s))",
        chat_log.id,
        user_id,
        fallback,
        len(citations),
    )
    return chat_log


__all__ = ["citation_rows", "save_chat"]
