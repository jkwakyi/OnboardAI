"""Login tokens are issued, and only ours are accepted (ON-36).

A token is the whole of the authorisation story: Auth Check (ON-14) will
decide who a request belongs to and whether their role may reach the
endpoint, with nothing but the token in front of it. So the interesting
tests here are not the ones where a good token is accepted - they are the
ones where a token that is nearly right is refused.
"""

import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import get_settings
from app.services.auth.tokens import (
    ALGORITHM,
    MIN_SECRET_LENGTH,
    REQUIRED_CLAIMS,
    ExpiredToken,
    InvalidToken,
    _development_secret,
    issue_token,
    read_token,
)

USER = {"email": "employee@onboardai.example", "full_name": "Alex Rivera", "role": "employee"}


def token_for_test(**overrides) -> str:
    """A valid token, unless a test overrides something in it."""
    return issue_token(overrides.pop("user_id", 7), **{**USER, **overrides})


# --- a good token ------------------------------------------------------


def test_a_token_says_who_its_holder_is(auth_env):
    claims = read_token(token_for_test())

    assert claims.user_id == 7
    assert claims.email == "employee@onboardai.example"
    assert claims.full_name == "Alex Rivera"
    assert claims.role == "employee"


def test_a_token_carries_an_expiry_one_working_day_out(auth_env):
    claims = read_token(token_for_test())

    assert claims.expires_at - claims.issued_at == timedelta(
        minutes=get_settings().auth_token_ttl_minutes
    )
    assert claims.expires_at > datetime.now(UTC)


def test_both_roles_can_hold_a_token(auth_env):
    for role in ("employee", "hr_administrator"):
        assert read_token(token_for_test(role=role)).role == role


def test_a_role_the_contracts_do_not_define_is_never_issued(auth_env):
    """Issuing is where this is cheapest to stop."""
    with pytest.raises(ValueError, match="not one of the roles"):
        token_for_test(role="superuser")


# --- tokens that are nearly right --------------------------------------


def test_an_expired_token_is_refused(auth_env):
    ttl = get_settings().auth_token_ttl_minutes
    stale = token_for_test(issued_at=datetime.now(UTC) - timedelta(minutes=ttl + 1))

    with pytest.raises(ExpiredToken):
        read_token(stale)


def test_an_expired_token_is_told_apart_from_a_bad_one(auth_env):
    """So the Login Page can say "your session ended" and mean it."""
    assert issubclass(ExpiredToken, InvalidToken)


def test_a_token_signed_with_another_key_is_refused(auth_env):
    forged = jwt.encode(
        {
            "sub": "7",
            "iss": get_settings().auth_token_issuer,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "email": USER["email"],
            "name": USER["full_name"],
            "role": "hr_administrator",
        },
        "a key that is not ours but is long enough to pass",
        algorithm=ALGORITHM,
    )

    with pytest.raises(InvalidToken):
        read_token(forged)


def test_an_unsigned_token_is_refused(auth_env):
    """The oldest JWT attack: a token that nominates "alg": "none"."""
    unsigned = jwt.encode(
        {
            "sub": "7",
            "iss": get_settings().auth_token_issuer,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "email": USER["email"],
            "name": USER["full_name"],
            "role": "hr_administrator",
        },
        key="",
        algorithm="none",
    )

    with pytest.raises(InvalidToken):
        read_token(unsigned)


def test_a_token_from_another_issuer_is_refused(auth_env, monkeypatch):
    ours = token_for_test()
    monkeypatch.setenv("AUTH_TOKEN_ISSUER", "somebody-elses-onboardai")
    get_settings.cache_clear()

    with pytest.raises(InvalidToken):
        read_token(ours)


def test_an_employee_cannot_promote_themselves_by_editing_their_token(auth_env):
    """The attack the signature exists for.

    A JWT payload is base64, not encryption: anyone holding a token can
    read it and rewrite it. What they cannot do is sign the result.
    """
    header, payload, signature = token_for_test(role="employee").split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["role"] = "hr_administrator"
    rewritten = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")

    with pytest.raises(InvalidToken):
        read_token(f"{header}.{rewritten}.{signature}")


@pytest.mark.parametrize("missing", REQUIRED_CLAIMS)
def test_a_token_missing_any_required_claim_is_refused(auth_env, missing):
    """Above all `exp`: a token with no expiry would never stop working."""
    payload = {
        "sub": "7",
        "iss": get_settings().auth_token_issuer,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "email": USER["email"],
        "name": USER["full_name"],
        "role": USER["role"],
    }
    del payload[missing]
    incomplete = jwt.encode(
        payload,
        get_settings().auth_secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )

    with pytest.raises(InvalidToken):
        read_token(incomplete)


def test_a_signed_token_carrying_an_unknown_role_is_refused(auth_env):
    """The roles changed under a token that is still in somebody's browser.

    An unknown role is not a smaller set of permissions. It is an unknown
    one, so the token does not come in.
    """
    smuggled = jwt.encode(
        {
            "sub": "7",
            "iss": get_settings().auth_token_issuer,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "email": USER["email"],
            "name": USER["full_name"],
            "role": "superuser",
        },
        get_settings().auth_secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )

    with pytest.raises(InvalidToken):
        read_token(smuggled)


@pytest.mark.parametrize("rubbish", ["", "   ", "not.a.token", "a.b", "....", "Bearer abc"])
def test_anything_that_is_not_a_token_is_refused(auth_env, rubbish):
    with pytest.raises(InvalidToken):
        read_token(rubbish)


def test_a_rejection_does_not_explain_itself_to_the_caller(auth_env):
    """The difference between a bad signature and a wrong issuer is useful
    to whoever is probing and to nobody else. It goes to the log."""
    with pytest.raises(InvalidToken) as refused:
        read_token("not.a.token")

    assert str(refused.value) == "the login token could not be verified"


# --- the signing key ---------------------------------------------------


def test_a_short_signing_key_is_refused_outright(auth_env, monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "short")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match=f"at least {MIN_SECRET_LENGTH}"):
        token_for_test()


def test_production_will_not_start_without_a_signing_key(monkeypatch):
    monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    monkeypatch.setenv("ONBOARDAI_ENV", "production")
    get_settings.cache_clear()
    _development_secret.cache_clear()

    try:
        with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY is not set"):
            token_for_test()
    finally:
        get_settings.cache_clear()
        _development_secret.cache_clear()


def test_development_falls_back_to_a_key_that_lasts_one_process(monkeypatch, caplog):
    """Random per process, so it is never a secret anybody can look up -
    and the log says what that means for anybody whose session just ended."""
    monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    monkeypatch.setenv("ONBOARDAI_ENV", "development")
    get_settings.cache_clear()
    _development_secret.cache_clear()

    try:
        with caplog.at_level("WARNING"):
            first = token_for_test()
        second = token_for_test()

        assert read_token(first).user_id == 7
        assert read_token(second).user_id == 7
        assert "AUTH_SECRET_KEY is not set" in caplog.text

        # A restart is a new key, so yesterday's token is not accepted.
        _development_secret.cache_clear()
        with pytest.raises(InvalidToken):
            read_token(first)
    finally:
        get_settings.cache_clear()
        _development_secret.cache_clear()
