"""Chat API.

Contract: POST /api/chat/ask, POST /api/chat/feedback. Both are the Chat
Page, both roles - Auth Check (ON-14) enforces that from its own table
before any of this runs.

`ask` is steps 1 to 9: the question arrives (step 1), Auth Check has
already run (step 2), the QA Controller takes it from there (steps 3 to
8), and the chat is saved through the Logging Service (step 9) before the
answer goes back. Feedback is the Feedback epic.

The one rule this endpoint exists to keep
-----------------------------------------
"A timeout, provider error or invalid output from the LLM is not an error
for the employee: POST /api/chat/ask returns fallback: true with a message
directing the employee to HR." So the AI path never produces a 4xx or a
5xx here. Everything it can do wrong - no good match, nothing retrieved,
the Embedding API down, the model timing out, output that fails the JSON
check - comes back as a 200 carrying `fallback: true`, and the QA
Controller has already made that translation.

What is still an error
----------------------
A question that is not a question (422), a token that is not valid (401),
and the Main Database refusing to record the chat (500). None of those is
the AI path. The last one is the arguable case and the reasoning is in
`ask` itself.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.auth_check import current_claims
from app.db.models import User
from app.db.session import get_session
from app.services.auth import TokenClaims
from app.services.llm.gateway import MAX_QUESTION_CHARACTERS
from app.services.logs import citation_rows, save_chat
from app.services.qa import QAController

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class AskRequest(BaseModel):
    """An employee's question.

    Bounded by the LLM Gateway's own limit rather than a number of this
    endpoint's own, so the two cannot drift apart. The Gateway truncates
    anything longer when it builds the prompt; a question that was
    silently answered from its first two thousand characters is a worse
    outcome than one that was refused, because the employee has no way to
    tell it happened.
    """

    question: str = Field(
        # No `min_length=1` beside this. The validator below already
        # refuses an empty string, since "".strip() is falsy, so the two
        # overlapped - and a redundant guard is worse than no guard when
        # it hides the loss of the one that matters: with both in place,
        # deleting the validator still left empty questions refused and
        # every test passing, while a question of three spaces would
        # have gone through to the model.
        max_length=MAX_QUESTION_CHARACTERS,
        description="The employee's question, in their own words.",
    )

    @field_validator("question")
    @classmethod
    def _must_say_something(cls, value: str) -> str:
        """`min_length` counts characters, and a space is a character."""
        if not value.strip():
            raise ValueError("The question cannot be blank.")
        return value


class CitationResponse(BaseModel):
    """A section an answer drew on, as the Chat Page shows it.

    `section_id` is what makes a citation followable - it is the only
    thing that still identifies a section after the text has been through
    a model - and the heading and document are what a person reads.
    """

    section_id: int
    heading: str | None = None
    document: str | None = None


class AskResponse(BaseModel):
    """The answer with its citations, or the HR fallback.

    `id` is the saved chat log. The Chat Page needs it for two things the
    contracts describe: rating the answer, and clicking "Send to HR" on a
    fallback so HR's reply comes back against the right message (E4). It
    is always a real row - see `ask`.
    """

    id: int
    answer: str
    citations: list[CitationResponse] = []
    fallback: bool


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a question and get an answer with citations",
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The question was blank or too long."
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "The chat could not be recorded."},
    },
)
def ask(
    body: AskRequest,
    session: Annotated[Session, Depends(get_session)],
    claims: Annotated[TokenClaims, Depends(current_claims)],
) -> AskResponse:
    """Answer an employee's question from the approved documents (steps 1 to 9)."""
    # The token says who this is; the table says whether they still exist.
    # A token outlives the account it names (TD-19), and `chat_logs` has a
    # foreign key to `users` that would fail far less legibly than this.
    asker = session.get(User, claims.user_id)
    if asker is None:
        logger.warning("token for user %s names an account that is gone", claims.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    question = body.question.strip()
    answer = QAController().ask(question, session)

    # Step 9. Saved before the answer goes back, and inside the request
    # rather than after it, because the response carries the row's id and
    # an id for a row that does not exist is worse than no id: the Chat
    # Page would offer "Send to HR" on a fallback and the escalation would
    # fail against a missing foreign key, in front of the employee, after
    # they had already been told to ask HR.
    #
    # So a failure here is a 500 and not a fallback. It is not the AI path
    # - retrieval read this same database successfully moments earlier, so
    # a write failing now is a real outage - and the contracts' rule about
    # never showing the employee an error is about the model, not about
    # the database being gone.
    try:
        chat_log = save_chat(
            session,
            user_id=asker.id,
            question=question,
            answer=answer.answer,
            citations=answer.citations,
            fallback=answer.fallback,
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception("could not record the chat for user %s", asker.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The answer could not be recorded. Please try again.",
        ) from None

    logger.info(
        "answered a question for user %s: fallback=%s, best score %s, %d section(s) retrieved",
        asker.id,
        answer.fallback,
        f"{answer.best_score:.3f}" if answer.best_score is not None else "none",
        answer.retrieved,
    )

    return AskResponse(
        id=chat_log.id,
        answer=answer.answer,
        citations=[CitationResponse(**row) for row in citation_rows(answer.citations)],
        fallback=answer.fallback,
    )
