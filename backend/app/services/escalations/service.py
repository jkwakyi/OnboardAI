"""The Escalation Service (ON-20, E1 to E2).

The contracts give it one line — "Called by the Escalations API; saves
the question as an open escalation in the Main Database (E2)" — and the
flow around it: "When an employee gets a fallback answer, they can click
Send to HR. The question is saved as an open escalation (E1, E2), the HR
administrator sees it in the HR Inbox, replies and marks it resolved
(E3), and the employee sees HR's reply in the chat page (E4)."

The question is not taken from the request
------------------------------------------
It is read out of the chat log the escalation points at. The caller
names which answer they are escalating; the server decides what was
asked. Those are the same thing when the page behaves, and they stop
being the same thing the moment anybody sends their own JSON — at which
point HR's inbox fills with questions nobody asked, each one looking
exactly like a real one, and the chat log it links to says something
else entirely.

Only a fallback can be escalated
--------------------------------
"Sends a question that got a fallback answer to HR". An answered
question has an answer already; escalating it would put a solved
question in front of HR with no indication that it was solved. The Chat
Page only draws the button on a fallback, but a button that is absent is
not a rule — this is.

Asking twice is not two escalations
-----------------------------------
A double click, a retried request, an impatient second press: all of
them arrive as a second POST for the same chat log. Rather than two rows
in HR's inbox saying the same thing, the existing open escalation comes
back. See TD-35 for what that does and does not guarantee.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChatLog, Escalation

logger = logging.getLogger(__name__)


class EscalationRefused(Exception):
    """The escalation cannot be created, and why in words for the employee."""


class NoSuchAnswer(EscalationRefused):
    """No chat log with that id belongs to this person.

    One error for "it does not exist" and "it is not yours" on purpose.
    Telling the difference apart is telling somebody which ids are real.
    """


class NotAFallback(EscalationRefused):
    """The answer being escalated is an answer."""


def open_escalation(session: Session, user_id: int, chat_log_id: int) -> Escalation:
    """Save the question behind `chat_log_id` as an open escalation (E2).

    Flushes rather than commits: the caller is mid-request and is the
    only thing that knows whether the whole of it succeeded.
    """
    chat_log = session.get(ChatLog, chat_log_id)

    # Auth Check guards routes, not rows (TD-21), so whether this answer
    # belongs to the person asking is this layer's question. Without it an
    # employee could escalate a colleague's conversation - and would see
    # HR's reply to it, since E4 shows a reply against the chat it
    # belongs to.
    if chat_log is None or chat_log.user_id != user_id:
        logger.info("user %s tried to escalate chat log %s", user_id, chat_log_id)
        raise NoSuchAnswer("That answer could not be found.")

    if not chat_log.fallback:
        raise NotAFallback("That question was answered, so there is nothing to send to HR.")

    existing = session.scalars(
        select(Escalation).where(
            Escalation.chat_log_id == chat_log_id,
            Escalation.user_id == user_id,
            Escalation.status == "open",
        )
    ).first()
    if existing is not None:
        logger.info("chat log %s is already with HR as escalation %s", chat_log_id, existing.id)
        return existing

    escalation = Escalation(
        user_id=user_id,
        chat_log_id=chat_log_id,
        # The question as it was asked, not as the caller describes it.
        question=chat_log.question,
        status="open",
    )
    session.add(escalation)
    session.flush()

    logger.info(
        "escalation %s opened by user %s for chat log %s", escalation.id, user_id, chat_log_id
    )
    return escalation


__all__ = ["EscalationRefused", "NoSuchAnswer", "NotAFallback", "open_escalation"]
