"""Escalations API.

Contract: POST /api/escalations, GET /api/escalations,
PATCH /api/escalations/{id}.

POST is ON-20 — E1 to E2, the "Send to HR" button on a fallback answer.
GET is ON-21 and ON-22 (the HR Inbox and the employee's own view of their
replies); PATCH is ON-21. Only POST is here, because only POST is built:
an endpoint that exists and does nothing is worse than one that is
absent, because a client finds it and believes it.

What this endpoint does not accept
----------------------------------
The question. The caller says which answer they are escalating and the
server reads what was asked out of the chat log, which is the only way
the question in HR's inbox is the question the employee actually asked.
The Escalation Service owns that rule and the two others worth having -
that the answer belongs to the person escalating it, and that it was a
fallback.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.auth_check import current_claims
from app.db.models import Escalation, User
from app.db.session import get_session
from app.services.auth import TokenClaims
from app.services.escalations import NoSuchAnswer, NotAFallback, open_escalation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/escalations", tags=["escalations"])


class EscalationRequest(BaseModel):
    """Which answer is being sent to HR.

    One field. The question comes from the chat log named here - see the
    module docstring - and the status is always `open`, because E2 says
    so and an employee does not get to open a resolved one.
    """

    chat_log_id: int = Field(
        gt=0,
        description="The id from POST /api/chat/ask of the fallback answer being escalated.",
    )


class EscalationResponse(BaseModel):
    """An escalation, as the Chat Page sees it after sending.

    `hr_reply` and `resolved_at` are deliberately absent: a just-opened
    escalation has neither, and a field that is always null is a field
    somebody writes code against. They arrive with the endpoints that can
    fill them (ON-21, ON-22).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_log_id: int | None
    question: str
    status: str
    created_at: datetime


@router.post(
    "",
    response_model=EscalationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a question that got a fallback answer to HR",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "No such answer, or it is not yours."},
        status.HTTP_409_CONFLICT: {"description": "That question was answered."},
    },
)
def send_to_hr(
    body: EscalationRequest,
    session: Annotated[Session, Depends(get_session)],
    claims: Annotated[TokenClaims, Depends(current_claims)],
) -> Escalation:
    """Save a fallback question as an open escalation (E1, E2)."""
    # The token says who this is; the table says whether they still exist.
    # A token outlives the account it names (TD-19), and `escalations` has
    # a foreign key to `users` that would fail far less legibly than this.
    asker = session.get(User, claims.user_id)
    if asker is None:
        logger.warning("token for user %s names an account that is gone", claims.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        escalation = open_escalation(session, user_id=asker.id, chat_log_id=body.chat_log_id)
        session.commit()
    except NoSuchAnswer as missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(missing)) from missing
    except NotAFallback as answered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(answered)
        ) from answered
    except SQLAlchemyError:
        session.rollback()
        logger.exception("could not save the escalation for user %s", asker.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The question could not be sent to HR. Please try again.",
        ) from None

    return escalation
