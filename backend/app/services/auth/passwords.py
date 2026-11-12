"""Password hashing for the Auth Service (ON-36).

The Interface Contracts say passwords are stored hashed, and the users
table has nowhere to put a plain one. This module is the only thing in the
backend that turns a password into something storable, and the only thing
that checks one back.

scrypt, from the standard library
---------------------------------
`hashlib.scrypt` is memory-hard: an attacker with a GPU farm cannot trade
memory for parallelism the way they can against PBKDF2 or a bare SHA. It is
also already present wherever CPython is, which matters for a team that
develops on Windows and runs CI on Linux - a hashing library that needs a
compiler is a hashing library somebody eventually works around.

The cost parameters are n=16384, r=8, p=5, which is one of the settings
OWASP lists as equivalent minimum work for scrypt. The reason for *that*
row of the table rather than the more familiar n=131072, r=8, p=1 is
mechanical: OpenSSL refuses a scrypt call asking for more than 32 MiB
unless it is told otherwise, and 128 * n * r is 16 MiB here against 128 MiB
there. Raising the memory ceiling to clear a parameter nobody can run
without raising it is how a default stops being a default.

The parameters travel inside the stored hash
--------------------------------------------
A stored hash reads

    $scrypt$n=16384,r=8,p=5$<salt>$<key>

so the cost can be raised later without locking anybody out: an old hash
still carries the parameters it was made with, `verify_password` uses
those, and `needs_rehash` reports that the stored hash is now below what
this deployment asks for. A hash format that only works for one set of
parameters is a format that can never be strengthened.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings

# The identifier at the front of every stored hash. Anything else is either
# from a different scheme or not a hash at all, and is refused rather than
# guessed at.
SCHEME = "scrypt"

# 16 bytes, which is what RFC 7914 suggests and what rules out two users
# with the same password sharing a hash.
SALT_BYTES = 16

# 256 bits of derived key. Longer buys nothing: the comparison is the
# weakest link long before this is.
KEY_BYTES = 32

# scrypt's cost is independent of how long the password is, so a huge one is
# not a hashing problem - but reading an unbounded string into memory and
# normalising it is still work an unauthenticated caller can ask for. A
# thousand bytes is far past any real passphrase.
MAX_PASSWORD_BYTES = 1024


@dataclass(frozen=True)
class ScryptParams:
    """The three scrypt cost parameters, as stored and as applied."""

    n: int
    r: int
    p: int

    def __post_init__(self) -> None:
        if self.n < 2 or self.n & (self.n - 1):
            raise ValueError(f"scrypt n must be a power of two above 1, not {self.n}")
        if self.r < 1 or self.p < 1:
            raise ValueError(f"scrypt r and p must be positive, not r={self.r} p={self.p}")

    @property
    def memory_bytes(self) -> int:
        """How much memory one hash will ask for.

        OpenSSL's own accounting, not the familiar 128 * n * r: it allocates
        a p-wide input block as well as the n-element scratch array, and
        sizes that array for n + 2 elements. The difference is a rounding
        error at the default cost and the whole difference between working
        and "memory limit exceeded" at the edge, which is exactly where a
        cost parameter is chosen.
        """
        return 128 * self.r * self.p + 128 * self.r * (self.n + 2)

    def encode(self) -> str:
        """The parameters as they appear in a stored hash."""
        return f"n={self.n},r={self.r},p={self.p}"

    @classmethod
    def decode(cls, encoded: str) -> ScryptParams:
        """Read parameters back out of a stored hash."""
        values: dict[str, int] = {}
        for pair in encoded.split(","):
            name, separator, value = pair.partition("=")
            if not separator or name not in ("n", "r", "p") or name in values:
                raise ValueError(f"unreadable scrypt parameters: {encoded!r}")
            try:
                values[name] = int(value)
            except ValueError as error:
                raise ValueError(f"unreadable scrypt parameters: {encoded!r}") from error
        if set(values) != {"n", "r", "p"}:
            raise ValueError(f"unreadable scrypt parameters: {encoded!r}")
        return cls(**values)


def current_params() -> ScryptParams:
    """The cost this deployment hashes new passwords at.

    Read from settings rather than fixed, because the test suite hashes
    hundreds of passwords and 272 ms each would turn a fast offline suite
    into a slow one. Lowering it there is safe precisely because the
    parameters are stored per hash: a cheap test hash is never mistaken for
    a production one.
    """
    settings = get_settings()
    return ScryptParams(
        n=settings.password_scrypt_n,
        r=settings.password_scrypt_r,
        p=settings.password_scrypt_p,
    )


def _b64(raw: bytes) -> str:
    """Base64 with the padding stripped, as the PHC string format has it."""
    return base64.b64encode(raw).decode("ascii").rstrip("=")


def _unb64(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.b64decode(encoded + padding, validate=True)


def _normalise(password: str) -> bytes:
    """A password as bytes, in one canonical form.

    Two keyboards can produce the same accented character as one code point
    or as two, and somebody who set their password on one of them should
    still be able to log in from the other. NFKC picks one.
    """
    encoded = unicodedata.normalize("NFKC", password).encode("utf-8")
    if not encoded:
        raise ValueError("password must not be empty")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
    return encoded


def _derive(password: bytes, salt: bytes, params: ScryptParams) -> bytes:
    return hashlib.scrypt(
        password,
        salt=salt,
        n=params.n,
        r=params.r,
        p=params.p,
        dklen=KEY_BYTES,
        # Ask for exactly what this cost needs. Left at 0 the limit is
        # OpenSSL's 32 MiB, which the default parameters fit inside and a
        # future raised cost would not - and that failure then looks like a
        # broken install rather than a parameter that was never tried.
        maxmem=params.memory_bytes,
    )


def hash_password(password: str, *, params: ScryptParams | None = None) -> str:
    """Hash a password for storage, salt and parameters included.

    Raises ValueError for a password that is empty or absurdly long, which
    are both programming errors rather than failed logins. `verify_password`
    answers False for the same input instead of raising, because that one is
    reached by anybody who can type into a login form.
    """
    chosen = params or current_params()
    salt = secrets.token_bytes(SALT_BYTES)
    key = _derive(_normalise(password), salt, chosen)
    return f"${SCHEME}${chosen.encode()}${_b64(salt)}${_b64(key)}"


def _parse(stored: str) -> tuple[ScryptParams, bytes, bytes]:
    """Split a stored hash into parameters, salt and key."""
    parts = stored.split("$")
    # A leading "$" makes parts[0] empty; four fields follow it.
    if len(parts) != 5 or parts[0] != "" or parts[1] != SCHEME:
        raise ValueError("stored password hash is not in the expected format")
    params = ScryptParams.decode(parts[2])
    return params, _unb64(parts[3]), _unb64(parts[4])


def verify_password(password: str, stored: str) -> bool:
    """Is this the password that produced `stored`?

    Answers False rather than raising for anything malformed. A caller
    handling a login has nothing useful to do with the difference between a
    wrong password and a corrupt hash, and an exception escaping here would
    turn a bad password into a 500.
    """
    try:
        params, salt, expected = _parse(stored)
        candidate = _derive(_normalise(password), salt, params)
    except (ValueError, OverflowError, MemoryError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


def needs_rehash(stored: str) -> bool:
    """Was `stored` made with different parameters from the current ones?

    True also for a hash this module cannot read at all, which is the answer
    that gets a legacy or corrupt hash replaced the next time its owner logs
    in successfully.
    """
    try:
        params, _, _ = _parse(stored)
    except ValueError:
        return True
    current = current_params()
    return (params.n, params.r, params.p) != (current.n, current.r, current.p)


@lru_cache(maxsize=4)
def _decoy_hash_for(params: ScryptParams) -> str:
    """A well-formed hash that no password can match.

    Built rather than derived. A random key of the right width cannot be
    the output of any scrypt call anybody will make, so verifying against
    it does the full amount of work and always fails - and constructing it
    costs nothing, which is the point: hashing a throwaway password here
    would make the *first* unknown address after a restart cost twice what
    every later one costs, which is the timing signal this was meant to
    remove.
    """
    salt = secrets.token_bytes(SALT_BYTES)
    key = secrets.token_bytes(KEY_BYTES)
    return f"${SCHEME}${params.encode()}${_b64(salt)}${_b64(key)}"


def spend_verification_time() -> None:
    """Do a password verification that cannot succeed.

    Called when there is no account to check against. Without it, "no such
    email" returns in microseconds and a known email returns in a quarter of
    a second, which tells anybody with a stopwatch which addresses are
    registered. Spending the same work on nothing is the cheapest way to
    stop answering that question.
    """
    params = current_params()
    verify_password("not the password", _decoy_hash_for(params))


__all__ = [
    "KEY_BYTES",
    "MAX_PASSWORD_BYTES",
    "SALT_BYTES",
    "SCHEME",
    "ScryptParams",
    "current_params",
    "hash_password",
    "needs_rehash",
    "spend_verification_time",
    "verify_password",
]
