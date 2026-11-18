"""Login tokens for the Auth Service (ON-36).

The Interface Contracts give the login token one line - "issued at login
and sent with every request" - and list it as data moving between the Auth
Service, the Login API and the API Client. Nothing says where it is kept,
and the Main Database holds six things, none of them sessions. So the token
carries its own claims and a signature over them, and the server stores
nothing: Auth Check (ON-14) can answer "who is this and may they" from the
token alone, without a database round trip on every request.

JWT (RFC 7519) with HS256, through PyJWT, rather than a token format of our
own. The things that go wrong with hand-rolled tokens are not the signing -
that is one `hmac` call - they are the checks around it: accepting a token
that says it is unsigned, accepting an expired one because the comparison
was written the wrong way round, accepting one signed with the public half
of somebody else's key. PyJWT refuses all three, and a reviewer can check
that claim against a published standard instead of against this file.

A stateless token cannot be revoked
-----------------------------------
That is the trade, accepted for the alpha. The mitigation is a short
life: a token is good for one working day and then its holder logs in
again.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt

from app.config import Settings, get_settings
from app.db.models import ROLES

logger = logging.getLogger(__name__)

# The one algorithm this application issues and the one list it will accept.
# Passing the list to `jwt.decode` is what stops a token that nominates its
# own algorithm - "none", or an RSA public key used as an HMAC secret - from
# being verified on its own terms.
ALGORITHM = "HS256"

# Claims every token must carry. A token missing one of these is refused
# rather than treated as a token with that field absent, so a future change
# cannot quietly start issuing tokens that never expire.
REQUIRED_CLAIMS = ("sub", "iss", "iat", "exp", "email", "name", "role")

# A signing key shorter than this is refused. HS256 keys are hashed down to
# the block size anyway, so a short one is not a format error - it is just
# guessable, and the only moment anybody will see a complaint about it is
# when something refuses to start.
MIN_SECRET_LENGTH = 32


class InvalidToken(Exception):
    """The token is missing, unreadable, unsigned or not ours."""


class ExpiredToken(InvalidToken):
    """The token was ours and is past its expiry.

    Separate from `InvalidToken` so the Login Page can say "your session
    ended, sign in again" rather than "something was wrong with your
    request". Both are a 401.
    """


@dataclass(frozen=True)
class TokenClaims:
    """What a verified token says about its holder."""

    user_id: int
    email: str
    full_name: str
    role: str
    issued_at: datetime
    expires_at: datetime


@lru_cache(maxsize=1)
def _development_secret() -> str:
    """A signing key for a developer who has not set one.

    Random per process, so it is never a shared secret anybody could look
    up in the repository, and tokens stop working when the server restarts.
    That is the right trade for a machine where the alternative is either a
    committed key or a backend that refuses to start before the .env is
    filled in. Production gets no such fallback.
    """
    logger.warning(
        "AUTH_SECRET_KEY is not set, so login tokens are signed with a random "
        "key generated for this process. Tokens will stop working when the "
        "backend restarts. Set AUTH_SECRET_KEY in your .env (see "
        ".env.example) to keep sessions across restarts."
    )
    return secrets.token_urlsafe(48)


def _secret(settings: Settings) -> str:
    """The signing key, or an error that says how to supply one."""
    configured = settings.auth_secret_key
    value = configured.get_secret_value() if configured is not None else ""
    if value:
        if len(value) < MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"AUTH_SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters. "
                'Generate one with: python -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )
        return value
    if settings.onboardai_env == "production":
        raise RuntimeError(
            "AUTH_SECRET_KEY is not set. It is required when ONBOARDAI_ENV is "
            "production, because the development fallback signs tokens with a "
            "key that changes every restart. Generate one with: python -c "
            '"import secrets; print(secrets.token_urlsafe(48))" and put it in '
            "the server's own .env. Never commit it."
        )
    return _development_secret()


def issue_token(
    user_id: int,
    *,
    email: str,
    full_name: str,
    role: str,
    issued_at: datetime | None = None,
) -> str:
    """Sign a login token for one user.

    `issued_at` exists for the tests; left out it is now.
    """
    if role not in ROLES:
        raise ValueError(f"{role!r} is not one of the roles the contracts define: {ROLES}")

    settings = get_settings()
    now = issued_at or datetime.now(UTC)
    expires = now + timedelta(minutes=settings.auth_token_ttl_minutes)
    payload = {
        # RFC 7519 says `sub` is a string, and PyJWT enforces it.
        "sub": str(user_id),
        "iss": settings.auth_token_issuer,
        "iat": now,
        "exp": expires,
        "email": email,
        "name": full_name,
        "role": role,
    }
    return jwt.encode(payload, _secret(settings), algorithm=ALGORITHM)


def read_token(token: str) -> TokenClaims:
    """Verify a token and return what it says, or raise.

    Everything that can go wrong arrives here as one of two exceptions, so
    the only thing a caller has to decide is which message to show.
    """
    if not token:
        raise InvalidToken("no token was supplied")

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            _secret(settings),
            algorithms=[ALGORITHM],
            issuer=settings.auth_token_issuer,
            options={"require": list(REQUIRED_CLAIMS)},
        )
    except jwt.ExpiredSignatureError as error:
        raise ExpiredToken("the login token has expired") from error
    except jwt.InvalidTokenError as error:
        # Deliberately not repeating PyJWT's message to the caller: the
        # difference between a bad signature and a wrong issuer is useful to
        # whoever is attacking and to nobody else. The log keeps the detail.
        logger.info("rejected a login token: %s", error)
        raise InvalidToken("the login token could not be verified") from error

    role = payload["role"]
    if role not in ROLES:
        # A correctly signed token with a role this system does not define
        # means the roles changed under a token that is still in the wild.
        # Refusing it is the only safe reading: an unknown role is not a
        # smaller set of permissions, it is an unknown one.
        logger.warning("rejected a login token carrying unknown role %r", role)
        raise InvalidToken("the login token could not be verified")

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as error:
        raise InvalidToken("the login token could not be verified") from error

    return TokenClaims(
        user_id=user_id,
        email=payload["email"],
        full_name=payload["name"],
        role=role,
        issued_at=datetime.fromtimestamp(payload["iat"], UTC),
        expires_at=datetime.fromtimestamp(payload["exp"], UTC),
    )


__all__ = [
    "ALGORITHM",
    "MIN_SECRET_LENGTH",
    "REQUIRED_CLAIMS",
    "ExpiredToken",
    "InvalidToken",
    "TokenClaims",
    "issue_token",
    "read_token",
]
