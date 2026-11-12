"""Passwords are stored hashed, and nothing else gets in (ON-36).

ON-13's second acceptance criterion is one line - "passwords are stored
hashed" - and it is the line most easily satisfied in a way that does not
survive contact with an attacker. So these tests are not only "the right
password works": they pin the salt, the cost, the stored format, and every
way a caller can hand this module something it cannot read.

The cost is turned down by the `auth_env` fixture wherever a test only
needs hashing to happen. The one test that cares what the product actually
ships deliberately does not use it.
"""

import hashlib
import unicodedata

import pytest

from app.config import Settings
from app.services.auth.passwords import (
    KEY_BYTES,
    MAX_PASSWORD_BYTES,
    SALT_BYTES,
    SCHEME,
    ScryptParams,
    _parse,
    current_params,
    hash_password,
    needs_rehash,
    spend_verification_time,
    verify_password,
)

PASSWORD = "correct horse battery staple"


# --- the basics --------------------------------------------------------


def test_the_stored_hash_is_not_the_password(auth_env):
    stored = hash_password(PASSWORD)

    assert PASSWORD not in stored
    # Nor any prefix of it long enough to matter.
    assert "correct" not in stored


def test_the_right_password_verifies(auth_env):
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


@pytest.mark.parametrize(
    "wrong",
    [
        "correct horse battery stapl",
        "correct horse battery staple ",
        "Correct horse battery staple",
        "",
        "entirely different",
    ],
)
def test_a_wrong_password_does_not(auth_env, wrong):
    assert verify_password(wrong, hash_password(PASSWORD)) is False


def test_the_same_password_hashes_differently_every_time(auth_env):
    """A shared salt would let one cracked hash unlock every reuse of it."""
    hashes = {hash_password(PASSWORD) for _ in range(5)}

    assert len(hashes) == 5
    assert all(verify_password(PASSWORD, stored) for stored in hashes)


# --- the stored format -------------------------------------------------


def test_the_stored_hash_records_its_own_parameters(auth_env):
    stored = hash_password(PASSWORD)
    params, salt, key = _parse(stored)

    assert stored.startswith(f"${SCHEME}$")
    assert params == current_params()
    assert len(salt) == SALT_BYTES
    assert len(key) == KEY_BYTES


def test_the_stored_hash_fits_the_column(auth_env):
    """users.password_hash is VARCHAR(255) (ON-11).

    And still fits if the cost is raised far past anything plausible: only
    the parameter digits grow with it, never the salt or the derived key.
    """
    stored = hash_password(PASSWORD)
    assert len(stored) <= 255

    params, _, _ = _parse(stored)
    widened = stored.replace(params.encode(), ScryptParams(n=2**24, r=4096, p=256).encode())
    assert len(widened) <= 255


def test_a_hash_made_at_another_cost_still_verifies(auth_env):
    """The reason the parameters are in the string at all.

    Raising the cost must not lock out everybody who set their password
    before it was raised.
    """
    old = hash_password(PASSWORD, params=ScryptParams(n=16, r=1, p=1))

    assert verify_password(PASSWORD, old) is True
    assert verify_password("wrong", old) is False


# --- the shipped cost --------------------------------------------------


def test_the_shipped_cost_is_the_owasp_row_we_chose(monkeypatch):
    """Deliberately without `auth_env`: this is about what ships.

    n=16384, r=8, p=5 is one of OWASP's listed equivalents for scrypt. The
    familiar n=131072, r=8, p=1 asks for 128 MiB, which OpenSSL will not
    allocate without being told to override its own limit.
    """
    for name in ("PASSWORD_SCRYPT_N", "PASSWORD_SCRYPT_R", "PASSWORD_SCRYPT_P"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    shipped = ScryptParams(
        n=settings.password_scrypt_n,
        r=settings.password_scrypt_r,
        p=settings.password_scrypt_p,
    )

    assert (shipped.n, shipped.r, shipped.p) == (16384, 8, 5)
    assert 16 * 1024 * 1024 <= shipped.memory_bytes < 32 * 1024 * 1024


def test_the_shipped_cost_runs_under_openssls_own_memory_limit():
    """The check that would have caught the parameters we did not pick.

    `maxmem=0` means "OpenSSL's default", which is 32 MiB. A cost above it
    raises rather than running slowly, so a hash function configured past
    that line does not degrade - it stops.
    """
    hashlib.scrypt(b"x", salt=b"y" * 16, n=16384, r=8, p=1, dklen=32, maxmem=0)

    with pytest.raises(ValueError):
        hashlib.scrypt(b"x", salt=b"y" * 16, n=32768, r=8, p=1, dklen=32, maxmem=0)


def test_a_cost_above_that_limit_still_works_here(auth_env):
    """Because `_derive` asks for the memory its parameters need.

    If that argument were dropped, this is the test that would fail, and
    the one before it says why that matters.
    """
    expensive = ScryptParams(n=32768, r=8, p=1)
    assert expensive.memory_bytes > 32 * 1024 * 1024

    assert verify_password(PASSWORD, hash_password(PASSWORD, params=expensive)) is True


# --- what a caller can hand it -----------------------------------------


def test_an_accented_password_verifies_however_it_was_typed(auth_env):
    """The same character, composed on one keyboard and not on another."""
    composed = unicodedata.normalize("NFC", "pässwörd-ñ")
    decomposed = unicodedata.normalize("NFD", "pässwörd-ñ")
    assert composed != decomposed

    assert verify_password(decomposed, hash_password(composed)) is True


@pytest.mark.parametrize("rejected", ["", "x" * (MAX_PASSWORD_BYTES + 1)])
def test_hashing_refuses_an_empty_or_absurd_password(auth_env, rejected):
    with pytest.raises(ValueError):
        hash_password(rejected)


@pytest.mark.parametrize("rejected", ["", "x" * (MAX_PASSWORD_BYTES + 1)])
def test_but_verifying_one_answers_false_instead_of_raising(auth_env, rejected):
    """Anybody can type into a login form; nobody should get a 500 for it."""
    assert verify_password(rejected, hash_password(PASSWORD)) is False


@pytest.mark.parametrize(
    "malformed",
    [
        "",
        "not a hash at all",
        "$bcrypt$n=16,r=8,p=1$c2FsdA$a2V5",
        "$scrypt$n=16,r=8$c2FsdA$a2V5",
        "$scrypt$n=sixteen,r=8,p=1$c2FsdA$a2V5",
        "$scrypt$n=16,r=8,p=1$not base64!$a2V5",
        "$scrypt$n=16,r=8,p=1$c2FsdA",
        "$scrypt$n=0,r=8,p=1$c2FsdA$a2V5",
        "$scrypt$n=15,r=8,p=1$c2FsdA$a2V5",
    ],
)
def test_a_hash_this_module_cannot_read_verifies_as_false(auth_env, malformed):
    assert verify_password(PASSWORD, malformed) is False


# --- parameters --------------------------------------------------------


@pytest.mark.parametrize("n", [0, 1, 15, 100, -16])
def test_n_must_be_a_power_of_two(n):
    with pytest.raises(ValueError):
        ScryptParams(n=n, r=8, p=1)


@pytest.mark.parametrize(("r", "p"), [(0, 1), (1, 0), (-1, 1)])
def test_r_and_p_must_be_positive(r, p):
    with pytest.raises(ValueError):
        ScryptParams(n=16, r=r, p=p)


def test_parameters_survive_a_round_trip():
    params = ScryptParams(n=16384, r=8, p=5)

    assert ScryptParams.decode(params.encode()) == params


@pytest.mark.parametrize(
    "junk", ["", "n=16", "n=16,r=8", "n=16,r=8,p=1,q=2", "n=16,n=16,r=8,p=1", "16,8,1"]
)
def test_unreadable_parameters_raise(junk):
    with pytest.raises(ValueError):
        ScryptParams.decode(junk)


# --- rehashing ---------------------------------------------------------


def test_a_current_hash_does_not_need_rehashing(auth_env):
    assert needs_rehash(hash_password(PASSWORD)) is False


def test_a_hash_at_another_cost_does(auth_env):
    assert needs_rehash(hash_password(PASSWORD, params=ScryptParams(n=1024, r=8, p=1))) is True


def test_so_does_a_hash_that_cannot_be_read(auth_env):
    """A legacy or corrupt hash is replaced the next time its owner logs in."""
    assert needs_rehash("not a hash at all") is True


# --- the timing of a failed login --------------------------------------


def test_the_unknown_account_path_really_does_the_work(auth_env, monkeypatch):
    """Not a timing measurement - a check that the work is requested.

    A timing assertion on a shared CI runner is a flaky test. What can be
    asserted without flakiness is that the decoy verification is a real
    verification of a real hash, which is what makes the two paths cost the
    same.
    """
    calls: list[tuple[str, str]] = []
    real = verify_password

    def recording(password, stored):
        calls.append((password, stored))
        return real(password, stored)

    monkeypatch.setattr("app.services.auth.passwords.verify_password", recording)
    spend_verification_time()

    assert len(calls) == 1
    _, decoy = calls[0]
    params, salt, key = _parse(decoy)
    assert params == current_params()
    assert len(salt) == SALT_BYTES
    assert len(key) == KEY_BYTES


def test_it_costs_the_same_the_first_time_as_every_other_time(auth_env, monkeypatch):
    """One scrypt derivation per call, including the first.

    Hashing a throwaway password to build the decoy would make the first
    unknown address after a restart cost two derivations and every later
    one cost a single derivation - which is the timing signal the decoy
    exists to remove, reintroduced one layer down.
    """
    derivations: list[int] = []
    real = hashlib.scrypt

    def counting(*args, **kwargs):
        derivations.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr("app.services.auth.passwords.hashlib.scrypt", counting)

    spend_verification_time()
    first = len(derivations)
    spend_verification_time()
    second = len(derivations) - first

    assert first == 1
    assert second == 1
