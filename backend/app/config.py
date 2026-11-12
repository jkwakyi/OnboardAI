"""Application configuration, read from the environment.

Every value here comes from the environment or a local .env file. Nothing
secret is ever hard-coded or committed; .env.example documents the shape.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
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

    # Embedding API (ON-10): an external service the Embedding Client calls
    # over HTTPS. The key lives on the server only - never in the React app,
    # never in the repository. It is a SecretStr so that printing the
    # settings, or logging them in a traceback, shows a mask instead.
    embedding_provider: str = "openai"
    embedding_api_url: str = "https://api.openai.com/v1/embeddings"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    # A client-side guard so a hanging provider cannot hold a request open.
    # The 20-second timeout the contracts fix belongs to the LLM Gateway.
    embedding_timeout_seconds: float = 10.0
    embedding_api_key: SecretStr | None = None

    # LLM provider selection. "mock" keeps CI and teammates without the
    # model running; see the LLMProvider interface (ON-44) and ON-18.
    llm_provider: str = "mock"

    # Auth Service (ON-36): the key login tokens are signed with. Secret,
    # server-side only, never in the React app. Unset is allowed outside
    # production, where the Auth Service signs with a random per-process key
    # instead and says so in the log.
    auth_secret_key: SecretStr | None = None
    # One working day. A stateless token cannot be withdrawn, so its life is
    # the only limit on a leaked one (TD-19).
    auth_token_ttl_minutes: int = 720
    # The `iss` claim. A token issued by something else, or for a different
    # deployment, is refused even when the signature checks out.
    auth_token_issuer: str = "onboardai"

    # scrypt cost. The defaults are 16 MiB and roughly a quarter of a second
    # per hash; the test suite turns them down, which is safe because every
    # stored hash records the parameters it was made with. See
    # app/services/auth/passwords.py for why this row of OWASP's table.
    password_scrypt_n: int = 16384
    password_scrypt_r: int = 8
    password_scrypt_p: int = 5

    # Login API (ON-37): how often one address, or one client, may fail
    # before being asked to wait. Checked before any password hashing, so
    # it limits both guessing and the CPU a caller can make the server
    # spend. In process, so per worker (TD-20).
    login_max_attempts: int = 10
    login_attempt_window_seconds: int = 900

    # The two synthetic accounts the seed script creates (ON-36). Addresses
    # and names are not secret and have defaults; the passwords have none,
    # so the only copy of a development password is in somebody's own .env.
    seed_employee_email: str = "employee@onboardai.example"
    seed_employee_name: str = "Alex Rivera"
    seed_employee_password: SecretStr | None = None
    seed_hr_email: str = "hr@onboardai.example"
    seed_hr_name: str = "Jordan Blake"
    seed_hr_password: SecretStr | None = None

    @field_validator("embedding_api_url")
    @classmethod
    def _embedding_api_url_must_be_https(cls, value: str) -> str:
        """The Interface Contracts say the Embedding API is called over HTTPS."""
        if not value.startswith("https://"):
            raise ValueError(
                "EMBEDDING_API_URL must be an https:// URL; the Interface "
                "Contracts say the Embedding Client calls the Embedding API "
                "over HTTPS"
            )
        return value

    @property
    def storage_path(self) -> Path:
        """File storage directory as an absolute path."""
        if self.file_storage_dir.is_absolute():
            return self.file_storage_dir
        return REPO_ROOT / self.file_storage_dir

    def require_embedding_api_key(self) -> str:
        """The Embedding API key, or an error that says how to supply it.

        Callers get the plain value only here, at the point of use, so the
        secret is never carried around in ordinary application state.
        """
        if self.embedding_api_key is None or not self.embedding_api_key.get_secret_value():
            raise RuntimeError(
                "EMBEDDING_API_KEY is not set. Put it in your own .env at the "
                "repository root (see .env.example). .env is ignored by Git "
                "and must never be committed."
            )
        return self.embedding_api_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Return the settings singleton."""
    return Settings()
