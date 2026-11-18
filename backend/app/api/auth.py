"""Login API (ON-37).

Contract: POST /api/auth/login - "Login credentials in, login token out.
Passwords are stored hashed."

The endpoint does three things and no more: it limits how often a caller
may fail, it asks the Auth Service whether these credentials belong to
somebody, and it returns that person's login token. Everything about how a
password is checked or a token is signed is behind `app.services.auth`
(ON-36), which is why this file has no cryptography in it.

What comes back is the token and nothing else, because that is what the
contracts say comes back. The token's claims already carry the holder's
name and role - the Login Page reads them from there to decide where to go
and what to show, and Auth Check (ON-14) is what actually enforces the
role on every later request. Returning them a second time in the body
would be a field the contracts do not define.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.throttle import AttemptLimiter, TooManyAttempts
from app.config import get_settings
from app.db.session import get_session
from app.services.auth import MAX_PASSWORD_BYTES, authenticate, normalise_email, token_for

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# One message for every way a login can fail. "No such account" and "wrong
# password" are the same answer here for the same reason they are the same
# answer inside the Auth Service: telling them apart turns the login form
# into a way to ask who works here.
CREDENTIALS_REJECTED = "The email address or password is incorrect."

_settings = get_settings()

# Two limits on the same request. The address keeps one person's account
# from being ground through a word list; the client keeps one machine from
# working through a list of addresses. Either alone leaves the other open.
login_limiter = AttemptLimiter(
    limit=_settings.login_max_attempts,
    window_seconds=_settings.login_attempt_window_seconds,
)


class LoginRequest(BaseModel):
    """Login credentials in.

    `extra="forbid"` so a body carrying anything else is a 422 rather than
    silently ignored - a client sending `"role": "hr_administrator"` and
    getting a 200 back would have every reason to think it had worked.
    """

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    # Bounded so an unauthenticated caller cannot hand the server an
    # arbitrarily large body to read and normalise. The lower bound is 1
    # because an empty password is a malformed request, not a wrong guess.
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)


class LoginResponse(BaseModel):
    """Login token out."""

    token: str


def _client_key(request: Request) -> str:
    """Which machine this request came from.

    Deliberately not X-Forwarded-For. Any caller can set that header, so
    trusting it would let an attacker hand themselves a fresh allowance on
    every request and turn the per-client limit into decoration. Behind a
    proxy this is the proxy, which is a known limitation of the alpha.
    """
    return f"client:{request.client.host if request.client else 'unknown'}"


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in and receive a login token",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": CREDENTIALS_REJECTED},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Too many failed attempts."},
    },
)
def login(
    credentials: LoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> LoginResponse:
    """Check credentials and issue a login token."""
    keys = (f"email:{normalise_email(credentials.email)}", _client_key(request))

    # Before any hashing. A limit checked afterwards still spends a quarter
    # of a second of one core on every refused request, which is the second
    # half of what this limit is for.
    for key in keys:
        try:
            login_limiter.check(key)
        except TooManyAttempts as refused:
            logger.warning("login refused by the attempt limit for %s", key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed sign-in attempts. Please wait and try again.",
                headers={"Retry-After": str(refused.retry_after_seconds)},
            ) from refused

    user = authenticate(session, credentials.email, credentials.password)
    if user is None:
        for key in keys:
            login_limiter.record_failure(key)
        # The address is logged; the password is not, here or anywhere.
        logger.info("rejected a login for %s", keys[0])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=CREDENTIALS_REJECTED,
        )

    for key in keys:
        login_limiter.clear(key)
    logger.info("issued a login token to user %s (%s)", user.id, user.role)
    return LoginResponse(token=token_for(user))
