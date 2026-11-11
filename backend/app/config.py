"""Application configuration, read from the environment.

Every value here comes from the environment or a local .env file. Nothing
secret is ever hard-coded or committed; .env.example documents the shape.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root, two levels above this file (backend/app/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Settings for the backend API."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    onboardai_env: str = "development"
    onboardai_log_level: str = "INFO"

    # Main Database (PostgreSQL): users, documents, sections, chat logs,
    # feedback, escalations.
    database_url: str = "postgresql+psycopg://onboardai:onboardai@localhost:5432/onboardai"

    # Vector Database (ChromaDB): section embeddings.
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "onboardai_sections"

    # File Storage: the original uploaded PDF/TXT files (U2).
    file_storage_dir: Path = Path("backend/storage/documents")

    # LLM provider selection. "mock" keeps CI and teammates without the
    # model running; see the LLMProvider interface (ON-44) and ON-18.
    llm_provider: str = "mock"

    @property
    def storage_path(self) -> Path:
        """File storage directory as an absolute path."""
        if self.file_storage_dir.is_absolute():
            return self.file_storage_dir
        return REPO_ROOT / self.file_storage_dir


@lru_cache
def get_settings() -> Settings:
    """Return the settings singleton."""
    return Settings()
