"""Configuration comes from the environment, with safe local defaults."""

from app.config import Settings


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
