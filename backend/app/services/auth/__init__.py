"""The Auth Service (ON-36).

One of the components the Interface Contracts name: "Hashed passwords,
login tokens. Called by the Login API; its data is stored in the Main
Database." Everything the rest of the application needs from it is
re-exported here, so the Login API (ON-37) and Auth Check (ON-14) import
`app.services.auth` and never reach past it into a submodule.

The three pieces inside:

* `passwords` - scrypt hashing, and the checks that go with it.
* `tokens` - signed login tokens, issued and verified.
* `accounts` - the Main Database side: finding a user, checking their
  credentials, and seeding the two synthetic development accounts.
"""

from app.services.auth.accounts import (
    SYNTHETIC_SUFFIXES,
    SeedAccount,
    SeedOutcome,
    SeedRefused,
    authenticate,
    ensure_account,
    find_user,
    normalise_email,
    seed,
    seed_accounts_from_settings,
    token_for,
)
from app.services.auth.passwords import (
    MAX_PASSWORD_BYTES,
    ScryptParams,
    current_params,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.services.auth.tokens import (
    ALGORITHM,
    MIN_SECRET_LENGTH,
    ExpiredToken,
    InvalidToken,
    TokenClaims,
    issue_token,
    read_token,
)

__all__ = [
    "ALGORITHM",
    "MAX_PASSWORD_BYTES",
    "MIN_SECRET_LENGTH",
    "SYNTHETIC_SUFFIXES",
    "ExpiredToken",
    "InvalidToken",
    "ScryptParams",
    "SeedAccount",
    "SeedOutcome",
    "SeedRefused",
    "TokenClaims",
    "authenticate",
    "current_params",
    "ensure_account",
    "find_user",
    "hash_password",
    "issue_token",
    "needs_rehash",
    "normalise_email",
    "read_token",
    "seed",
    "seed_accounts_from_settings",
    "token_for",
    "verify_password",
]
