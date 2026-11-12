"""Accounts: looking a user up, checking their password, seeding the two
synthetic development accounts (ON-36).

This is the half of the Auth Service that touches the Main Database. The
Login API (ON-37) calls `authenticate` and then `token_for`; the seed script
calls `ensure_account`. Nothing here knows about HTTP, which is why the
login behaviour can be tested without a server.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import ROLES, User
from app.services.auth.passwords import (
    hash_password,
    needs_rehash,
    spend_verification_time,
    verify_password,
)
from app.services.auth.tokens import issue_token

logger = logging.getLogger(__name__)

# Domains reserved by RFC 2606 and RFC 6761 for examples and tests. A
# seeded account must use one, so a demo account can never be an address
# that reaches a real person - which is what ON-36's "no real data" has to
# mean in practice, rather than a promise in a comment.
SYNTHETIC_SUFFIXES = (
    ".example",
    ".invalid",
    ".test",
    ".localhost",
    "@example.com",
    "@example.org",
    "@example.net",
)


class SeedRefused(Exception):
    """A seed account was asked for that would not be synthetic, or is
    missing its password, or was aimed at a production environment."""


@dataclass(frozen=True)
class SeedAccount:
    """One synthetic account to create or reset."""

    email: str
    full_name: str
    role: str
    password: str


@dataclass(frozen=True)
class SeedOutcome:
    """What happened to one seed account. Carries no password."""

    email: str
    role: str
    full_name: str
    created: bool

    def describe(self) -> str:
        return f"{'created' if self.created else 'reset'} {self.role}: {self.email}"


def normalise_email(email: str) -> str:
    """One canonical spelling of an address.

    The local part of an address is case-sensitive by the letter of the
    standard and case-insensitive at every mail provider anybody uses.
    Folding it means somebody who signed up as Jane@ can log in as jane@,
    and - because the column is unique - that the two cannot become two
    accounts.
    """
    return email.strip().lower()


def find_user(session: Session, email: str) -> User | None:
    """The account for an address, or None."""
    return session.scalars(select(User).where(User.email == normalise_email(email))).first()


def authenticate(session: Session, email: str, password: str) -> User | None:
    """The user these credentials belong to, or None.

    One return value for every kind of failure. A caller that could tell
    "no such account" from "wrong password" would eventually say so out
    loud, and then the login form answers questions about who works here.

    A successful login whose stored hash was made with different cost
    parameters is re-hashed in passing. That is the only moment the plain
    password is in hand, so it is the only moment the upgrade can happen.
    """
    user = find_user(session, email)
    if user is None:
        # Spend the time anyway - see spend_verification_time.
        spend_verification_time()
        return None

    if not verify_password(password, user.password_hash):
        return None

    if needs_rehash(user.password_hash):
        _upgrade_hash(session, user, password)

    return user


def _upgrade_hash(session: Session, user: User, password: str) -> None:
    """Re-hash a verified password at the current cost.

    A failure here must not fail the login: the password was correct, and
    the stored hash that is merely out of date still verifies it. So this
    rolls back and logs rather than propagating.
    """
    try:
        user.password_hash = hash_password(password)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.warning(
            "could not re-hash the password for user %s at the current cost; "
            "the login stands and the old hash remains",
            user.id,
            exc_info=True,
        )


def token_for(user: User) -> str:
    """A login token for an authenticated user."""
    return issue_token(
        user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
    )


def ensure_account(
    session: Session,
    *,
    email: str,
    full_name: str,
    role: str,
    password: str,
) -> SeedOutcome:
    """Create the account, or reset the one that is already there.

    Idempotent on purpose: seeding is something a teammate runs again after
    dropping their database, or when they have forgotten the development
    password. Re-running it resets name, role and password rather than
    failing on the unique email.
    """
    if role not in ROLES:
        raise SeedRefused(f"{role!r} is not one of the roles the contracts define: {ROLES}")

    address = normalise_email(email)
    if not any(address.endswith(suffix) for suffix in SYNTHETIC_SUFFIXES):
        raise SeedRefused(
            f"refusing to seed {address!r}: a seeded account must use an address "
            "reserved for examples (RFC 2606/6761), such as one ending "
            f"{', '.join(SYNTHETIC_SUFFIXES)}. These accounts are synthetic and "
            "must never be able to reach a real mailbox."
        )
    if not password:
        raise SeedRefused(f"no password was supplied for {address!r}")

    user = find_user(session, address)
    created = user is None
    if user is None:
        user = User(email=address)
        session.add(user)

    user.full_name = full_name
    user.role = role
    user.password_hash = hash_password(password)
    session.commit()

    return SeedOutcome(email=address, role=role, full_name=full_name, created=created)


def seed_accounts_from_settings(settings: Settings | None = None) -> list[SeedAccount]:
    """The two synthetic accounts, as configured.

    Emails and names have defaults, because they are not secret and a
    teammate should not have to invent them. The passwords have none: they
    come from the environment, so the only place a development password is
    written down is somebody's own .env.
    """
    settings = settings or get_settings()
    missing = [
        name
        for name, value in (
            ("SEED_EMPLOYEE_PASSWORD", settings.seed_employee_password),
            ("SEED_HR_PASSWORD", settings.seed_hr_password),
        )
        if value is None or not value.get_secret_value()
    ]
    if missing:
        raise SeedRefused(
            f"{' and '.join(missing)} must be set before seeding. Copy "
            ".env.example to .env and choose a password for each. There is "
            "deliberately no default: a password written into a tracked file "
            "is a password every checkout of this repository shares."
        )

    return [
        SeedAccount(
            email=settings.seed_employee_email,
            full_name=settings.seed_employee_name,
            role="employee",
            password=settings.seed_employee_password.get_secret_value(),
        ),
        SeedAccount(
            email=settings.seed_hr_email,
            full_name=settings.seed_hr_name,
            role="hr_administrator",
            password=settings.seed_hr_password.get_secret_value(),
        ),
    ]


def seed(session: Session, settings: Settings | None = None) -> list[SeedOutcome]:
    """Create or reset both synthetic accounts.

    Refuses outright in a production environment. Synthetic accounts with
    passwords out of a .env file have one purpose - letting the team and the
    graders sign in to a demo - and a production database is the one place
    that purpose does not apply.
    """
    settings = settings or get_settings()
    if settings.onboardai_env == "production":
        raise SeedRefused(
            "refusing to seed synthetic accounts while ONBOARDAI_ENV is "
            "production. These accounts exist for development and the demo; "
            "a real deployment gets real accounts."
        )

    return [
        ensure_account(
            session,
            email=account.email,
            full_name=account.full_name,
            role=account.role,
            password=account.password,
        )
        for account in seed_accounts_from_settings(settings)
    ]


__all__ = [
    "SYNTHETIC_SUFFIXES",
    "SeedAccount",
    "SeedOutcome",
    "SeedRefused",
    "authenticate",
    "ensure_account",
    "find_user",
    "normalise_email",
    "seed",
    "seed_accounts_from_settings",
    "token_for",
]
