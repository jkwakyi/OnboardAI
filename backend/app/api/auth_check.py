"""Auth Check (ON-14).

The component the architecture diagram puts at step 2: "Every request from
the API Client passes through it", and the Interface Contracts say it
"checks the token and role before the request reaches an endpoint".

It is one dependency, attached once to the router that carries the `/api`
prefix, so it runs for every endpoint mounted there - including the eight
that do not exist yet. That placement is the whole point. A check added per
endpoint is a check somebody forgets on the ninth, and the endpoint that
gets forgotten is never the one anybody would have guessed.

Fail closed
-----------
`ENDPOINT_ROLES` lists which roles may reach each of the nine endpoints the
contracts define. A request for a path that is *not* in that table is
refused rather than allowed: a new route that nobody thought about should
stop working, not quietly open. Forgetting a row then costs five minutes of
confusion, where the other way round costs an unnoticed hole.

What it does not do
-------------------
It answers "is this a real token, and may this role reach this endpoint" -
nothing finer. Whether *this* employee may see *that* escalation is a
question about rows, not routes, and it belongs to the endpoint that reads
them (ON-16, ON-21). Auth Check is the door, not the filing cabinet.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.models import ROLES
from app.services.auth import ExpiredToken, InvalidToken, TokenClaims, read_token

logger = logging.getLogger(__name__)

EMPLOYEE = "employee"
HR = "hr_administrator"

# Every role there is. Spelled from the model rather than written out, so a
# role added to the system cannot be silently missing from the one place
# that decides who gets in.
BOTH_ROLES = frozenset(ROLES)
HR_ONLY = frozenset({HR})

# No token needed. Exactly one endpoint: the one you use to get a token.
PUBLIC: frozenset[str] = frozenset()

# The nine endpoints, and who may reach each. Taken from the "Used by"
# column of the Interface Contracts: a page marked "(HR administrator)" is
# an HR-only endpoint, and a row naming both the HR Inbox Page and the Chat
# Page is open to both roles.
ENDPOINT_ROLES: dict[tuple[str, str], frozenset[str]] = {
    ("POST", "/api/auth/login"): PUBLIC,
    # Admin Upload Page (HR administrator).
    ("POST", "/api/documents"): HR_ONLY,
    ("GET", "/api/documents"): HR_ONLY,
    ("DELETE", "/api/documents/{id}"): HR_ONLY,
    # Chat Page. The contracts put the HR administrator on it too, and the
    # shell (ON-65) gives both roles the chat page, so an administrator
    # asking a question is not an error.
    ("POST", "/api/chat/ask"): BOTH_ROLES,
    ("POST", "/api/chat/feedback"): BOTH_ROLES,
    # Chat Page ("Send to HR" button).
    ("POST", "/api/escalations"): BOTH_ROLES,
    # "The HR Inbox lists the questions sent to HR (E3), and the employee
    # sees HR's reply in the chat page (E4)" - one endpoint, both readers.
    # Which rows each of them gets back is the endpoint's business, not
    # this one's.
    ("GET", "/api/escalations"): BOTH_ROLES,
    # HR Inbox Page (HR administrator).
    ("PATCH", "/api/escalations/{id}"): HR_ONLY,
}

MISSING_TOKEN = "This request needs a login token."
INVALID_TOKEN = "The login token could not be verified."
EXPIRED_TOKEN = "Your session has ended. Please sign in again."
WRONG_ROLE = "Your role does not have access to this."
NO_RULE = "This endpoint has no access rule and is refused."

# Sent with a 401 so a client knows what kind of credential is wanted.
# RFC 6750; the scheme is the only part of it this application uses.
BEARER = "Bearer"


def _unauthorised(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": BEARER},
    )


# Only the Bearer scheme, and only from the Authorization header. A token
# in a query string would end up in access logs, browser history and the
# Referer header of every link the page carries, which is three places a
# login token has no business being.
#
# auto_error=False so a missing or malformed header falls through to this
# module's own 401 and its own wording, rather than FastAPI's. The reason
# to use FastAPI's class at all rather than reading the header by hand is
# the generated documentation: declaring the scheme is what puts the
# Authorize button on /docs, which is how anybody tries these endpoints by
# hand during a demo.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="The login token from POST /api/auth/login.",
)

BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    """The token, or a 401 saying one is needed.

    `credentials` is None when the header is absent, carries no value, or
    names a scheme other than Bearer - the scheme match is case-insensitive
    per RFC 7235, which is worth honouring because a client sending
    "bearer" is correct and would otherwise spend an afternoon finding out
    why it is not.
    """
    token = credentials.credentials.strip() if credentials is not None else ""
    if not token:
        raise _unauthorised(MISSING_TOKEN)
    return token


def _endpoint(request: Request) -> tuple[str, str]:
    """The method and the *route template* this request matched.

    The template, not the URL: `/api/documents/{id}` rather than
    `/api/documents/42`, so the table has one row per endpoint instead of
    one per document. Starlette puts the matched route in the scope before
    any dependency runs.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None) or request.url.path
    return request.method.upper(), path


def auth_check(request: Request, credentials: BearerCredentials = None) -> TokenClaims | None:
    """Check the token and the role before the endpoint runs.

    Returns the claims, which are also left on `request.state.claims` so an
    endpoint can reach them through `current_claims` without repeating the
    verification.
    """
    method, path = _endpoint(request)

    try:
        allowed = ENDPOINT_ROLES[method, path]
    except KeyError:
        # Fail closed. Reaching here means a route exists that this table
        # has never heard of, which is either a new endpoint whose row was
        # forgotten or one the contracts do not define.
        logger.error("refusing %s %s: no access rule for this endpoint", method, path)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=NO_RULE,
        ) from None

    if allowed == PUBLIC:
        request.state.claims = None
        return None

    token = bearer_token(credentials)
    try:
        claims = read_token(token)
    except ExpiredToken as expired:
        raise _unauthorised(EXPIRED_TOKEN) from expired
    except InvalidToken as invalid:
        # The reason is in the Auth Service's log already. Repeating it to
        # the caller tells whoever is probing which part of their forgery
        # to fix next.
        raise _unauthorised(INVALID_TOKEN) from invalid

    if claims.role not in allowed:
        logger.info(
            "refused %s %s for user %s: role %s, needs one of %s",
            method,
            path,
            claims.user_id,
            claims.role,
            sorted(allowed),
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=WRONG_ROLE)

    request.state.claims = claims
    return claims


def current_claims(request: Request) -> TokenClaims:
    """Who this request belongs to, for an endpoint that needs to know.

    Reads what `auth_check` already verified rather than verifying again.
    Raises if it is called on a public endpoint, because an endpoint that
    needs to know who is asking is not a public endpoint and the mismatch
    is a programming error rather than something to answer at runtime.
    """
    claims = getattr(request.state, "claims", None)
    if claims is None:
        raise RuntimeError(
            "current_claims was used on an endpoint Auth Check treats as "
            "public; give the endpoint a role rule in ENDPOINT_ROLES"
        )
    return claims


__all__ = [
    "BEARER",
    "BOTH_ROLES",
    "EMPLOYEE",
    "ENDPOINT_ROLES",
    "EXPIRED_TOKEN",
    "HR",
    "HR_ONLY",
    "INVALID_TOKEN",
    "MISSING_TOKEN",
    "NO_RULE",
    "PUBLIC",
    "WRONG_ROLE",
    "auth_check",
    "bearer_scheme",
    "bearer_token",
    "current_claims",
]
