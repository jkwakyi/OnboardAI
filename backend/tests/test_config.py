"""Configuration comes from the environment, with safe local defaults."""

import re

import pytest
from pydantic import ValidationError

from app.config import REPO_ROOT, Settings


def test_defaults_point_at_local_services():
    settings = Settings()
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.chroma_port == 8001
    assert settings.chroma_collection == "onboardai_sections"


def test_mock_llm_is_the_default_provider():
    """CI and teammates without the model must be able to run the system."""
    assert Settings().llm_provider == "mock"


def test_environment_overrides_defaults(monkeypatch):
    monkeypatch.setenv("CHROMA_HOST", "chroma.internal")
    monkeypatch.setenv("LLM_PROVIDER", "real")
    settings = Settings()
    assert settings.chroma_host == "chroma.internal"
    assert settings.llm_provider == "real"


def test_storage_path_is_absolute():
    assert Settings().storage_path.is_absolute()


# --- Embedding API (ON-10) ---------------------------------------------


def test_the_embedding_provider_is_chosen_and_hosted():
    """ON-10's decision, recorded where the code can see it."""
    settings = Settings()
    assert settings.embedding_provider == "openai"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimensions == 1536


def test_the_embedding_api_is_called_over_https():
    """The Interface Contracts fix this, so the setting enforces it."""
    assert Settings().embedding_api_url.startswith("https://")

    with pytest.raises(ValidationError):
        Settings(embedding_api_url="http://api.openai.com/v1/embeddings")


def test_no_embedding_key_by_default():
    """A checkout with no .env must not carry a key from anywhere."""
    assert Settings(_env_file=None).embedding_api_key is None


def test_a_missing_key_says_how_to_supply_it(monkeypatch):
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    with pytest.raises(RuntimeError, match="EMBEDDING_API_KEY"):
        settings.require_embedding_api_key()


def test_an_empty_key_counts_as_missing(monkeypatch):
    """`EMBEDDING_API_KEY=` left blank in .env is not a key."""
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    with pytest.raises(RuntimeError, match="EMBEDDING_API_KEY"):
        Settings().require_embedding_api_key()


def test_the_key_is_readable_at_the_point_of_use(monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_KEY", "sk-test-not-a-real-key")
    assert Settings().require_embedding_api_key() == "sk-test-not-a-real-key"


def test_printing_the_settings_does_not_print_the_key(monkeypatch):
    """A traceback or a debug print must not leak the key."""
    monkeypatch.setenv("EMBEDDING_API_KEY", "sk-test-not-a-real-key")
    settings = Settings()
    for rendering in (str(settings), repr(settings), str(settings.model_dump())):
        assert "sk-test-not-a-real-key" not in rendering


# --- the key stays out of the repository -------------------------------


SECRET_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")


def test_env_example_carries_no_key_value():
    """.env.example documents the shape; a value in it would be committed.

    _PASSWORD is in the list because of ON-36: the development accounts are
    synthetic, but a password written into a tracked file is a password
    every checkout of this repository shares, and the habit of putting one
    there is the thing worth refusing.
    """
    for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        name, _, value = stripped.partition("=")
        assert not (name.strip().endswith(SECRET_SUFFIXES) and value.strip()), (
            f".env.example holds a value for {name.strip()}"
        )


def test_dotenv_is_ignored_but_the_example_is_not():
    ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in [line.strip() for line in ignore]
    assert "!.env.example" in [line.strip() for line in ignore]


def test_no_secret_is_named_so_that_vite_would_ship_it():
    """Vite copies every VITE_-prefixed variable into the browser bundle.

    A key named VITE_EMBEDDING_API_KEY would be published to every employee
    who loads the chat page, which is exactly what ON-10 forbids.
    """
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for name in re.findall(r"^#?\s*(VITE_\w+)=", text, re.MULTILINE):
        assert not name.endswith(SECRET_SUFFIXES), f"{name} would be shipped to the browser"


# --- Auth Service (ON-36) ----------------------------------------------


def test_no_signing_key_by_default():
    """Same rule as the embedding key: a checkout carries no secret."""
    assert Settings(_env_file=None).auth_secret_key is None


def test_printing_the_settings_does_not_print_the_signing_key(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "not-a-real-signing-key-but-long-enough")
    settings = Settings()
    for rendering in (str(settings), repr(settings), str(settings.model_dump())):
        assert "not-a-real-signing-key-but-long-enough" not in rendering


def test_a_token_lasts_one_working_day():
    """A stateless token cannot be withdrawn, so its life is the only limit
    on a leaked one (TD-19)."""
    assert Settings().auth_token_ttl_minutes == 720


def test_tokens_are_issued_in_this_deployments_name():
    assert Settings().auth_token_issuer == "onboardai"


def test_the_seed_accounts_use_addresses_that_cannot_be_delivered():
    """RFC 2606 reserves .example, so no demo account can mail a stranger."""
    settings = Settings()
    assert settings.seed_employee_email.endswith(".example")
    assert settings.seed_hr_email.endswith(".example")


def test_no_seed_password_by_default():
    """The only copy of a development password is in somebody's own .env."""
    settings = Settings(_env_file=None)
    assert settings.seed_employee_password is None
    assert settings.seed_hr_password is None


def test_printing_the_settings_does_not_print_a_seed_password(monkeypatch):
    monkeypatch.setenv("SEED_HR_PASSWORD", "a-development-password")
    settings = Settings()
    for rendering in (str(settings), repr(settings), str(settings.model_dump())):
        assert "a-development-password" not in rendering
