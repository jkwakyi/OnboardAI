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

# The LLM Gateway's contractual 20 seconds, copied rather than imported:
# the LLM package reads this module, so importing it back would close the
# loop. `test_config.py` asserts this copy still matches the Gateway's.
GATEWAY_TIMEOUT_SECONDS = 20.0


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
    # How many sections go in one request to the Embedding API (ON-41). A
    # long handbook splits into hundreds of sections and the endpoint takes
    # a list, so this is the difference between a handful of round trips
    # and one per section. Larger batches share the one timeout above, so
    # this trades round trips against how much is lost when one fails.
    embedding_batch_size: int = 64

    # LLM provider selection. "mock" keeps CI and teammates without the
    # model running; see the LLMProvider interface (ON-44) and ON-18.
    llm_provider: str = "mock"

    # Where the local model is served, and which one (ON-18). Ollama on
    # the loopback address: no key, and the handbook text in the prompt
    # never leaves the machine.
    #
    # `qwen3:8b` was selected against the ticket's criteria over
    # `mistral:7b` and `llama3.2:latest`, measured on the real prompts the
    # Gateway builds. It answered all five test questions inside the
    # Gateway's 20 seconds (slowest 4.3s) with a verified citation each
    # time. `llama3.2` managed one of five - it cites the handbook's own
    # numbering ("4.1") rather than the section id the prompt gave it, and
    # the Gateway drops a citation it cannot match. `deepseek-r1:14b` is
    # not a candidate: its thinking traces fight the JSON check.
    llm_api_url: str = "http://127.0.0.1:11434/api/generate"
    llm_model: str = "qwen3:8b"
    # How long the model stays resident between questions. A cold load
    # measured 56 seconds, which is past the Gateway's limit, so an idle
    # deployment answers its first question with the HR fallback (TD-36).
    llm_keep_alive: str = "30m"
    # Not the contractual timeout - that is the LLM Gateway's 20 seconds,
    # enforced there. This only bounds how long a call the Gateway has
    # already given up on can sit holding a socket, so it is deliberately
    # the longer of the two.
    llm_timeout_seconds: float = 30.0

    # How good the best retrieved section has to be before the QA
    # Controller will ask the LLM anything at all (ON-46). Below this, the
    # contracts say to skip the LLM and return the HR fallback.
    #
    # A setting rather than a constant, unlike the top-5 cut and the
    # Gateway's 20 seconds: ON-46 says to start with a provisional value
    # and tune it in the evaluation story, and the right value depends on
    # the embedding model rather than on the design.
    #
    # The score is a cosine similarity, so it runs from 1.0 (the section
    # says the same thing as the question) down through 0.0 (nothing in
    # common) to -1.0.
    #
    # 0.22 is measured, not guessed: it is the value that best separated
    # the evaluation question set's twenty answerable questions from its
    # ten unanswerable ones, over the real stack. It lets every answerable
    # question through. It also lets six of the ten unanswerable ones
    # through, because the two score distributions overlap - the best
    # unanswerable question outscores the median answerable one - so a
    # threshold alone cannot do this job. What catches the rest is the LLM
    # Gateway dropping an answer that cites nothing it was given. All of
    # this was measured against the *mock* embedder, which is lexical;
    # the hosted model's distribution has never been seen, because the
    # account has no credit. See TD-30.
    relevance_threshold: float = 0.22

    # Which origins the browser may call this API from (ON-38).
    #
    # Comma-separated, because a .env file holding JSON is a .env file
    # people get wrong. Both Vite ports by default: it moves to 5174 when
    # 5173 is taken, which happens whenever a second dev server is already
    # running, and a CORS failure looks exactly like the backend being down.
    #
    # Never "*". The browser will not send an Authorization header to a
    # wildcard origin with credentials, and more to the point a wildcard
    # says any site may call this API with whatever token the person
    # holding it has.
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:5174"

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

    # Document upload (ON-39). Applied while writing rather than read off
    # the Content-Length header, which the client also sets. 10 MB is far
    # past any HR policy document and well short of anything that would
    # fill a disk by accident.
    max_upload_bytes: int = 10 * 1024 * 1024

    # Reading an uploaded document (ON-40). ON-39 bounds what arrives;
    # these bound what it costs to read, which was the other half TD-22
    # was waiting on. A PDF is a program of sorts and a small one can ask
    # for a great deal of work, so extraction stops at a page count, a
    # character count and a wall clock, whichever comes first.
    pdf_max_pages: int = 200
    extraction_max_characters: int = 1_000_000
    # Its own number, not the LLM Gateway's 20 seconds - the two limits
    # bound different things and should be able to move apart.
    extraction_timeout_seconds: float = 15.0

    # How big a section is. A section is what gets a vector, what retrieval
    # returns five of, and what a citation points at, so the size is a
    # retrieval decision rather than a storage one: large enough to carry
    # an answer, small enough that five of them are about one subject.
    section_max_characters: int = 1500
    section_min_characters: int = 200

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

    @field_validator("embedding_batch_size")
    @classmethod
    def _embedding_batch_size_must_be_positive(cls, value: int) -> int:
        """A batch of nothing would send no sections and report success."""
        if value < 1:
            raise ValueError("EMBEDDING_BATCH_SIZE must be at least 1")
        return value

    @field_validator("llm_timeout_seconds")
    @classmethod
    def _llm_timeout_must_outlast_the_gateway(cls, value: float) -> float:
        """Shorter than the Gateway's limit and this becomes the timeout.

        The contracts fix the wait at 20 seconds and put it in the
        Gateway. A socket timeout below that would cut the provider off
        first, so every slow answer would be reported as a provider error
        rather than a timeout - the employee sees the same fallback either
        way, but ON-24's measurements and the log would both be wrong
        about which of the two happened.

        `GATEWAY_TIMEOUT_SECONDS` is a copy of the Gateway's constant
        rather than an import, because importing the LLM package from
        configuration would make the two import each other. A test
        asserts the copy still matches.
        """
        if value <= GATEWAY_TIMEOUT_SECONDS:
            raise ValueError(
                f"LLM_TIMEOUT_SECONDS is {value}, which is not longer than the "
                f"LLM Gateway's contractual {GATEWAY_TIMEOUT_SECONDS} seconds; "
                f"the Gateway is what gives up on a slow model, and this only "
                f"bounds the call it has abandoned"
            )
        return value

    @field_validator("relevance_threshold")
    @classmethod
    def _relevance_threshold_must_be_reachable(cls, value: float) -> float:
        """A cosine similarity cannot leave [-1, 1], so a threshold outside
        it is a typo rather than a strict policy - and the symptom of one
        above 1.0 is every employee getting the HR fallback forever, with
        nothing anywhere saying why.
        """
        if not -1.0 <= value <= 1.0:
            raise ValueError(
                f"RELEVANCE_THRESHOLD is {value}, which no cosine similarity can "
                f"reach; it must be between -1.0 and 1.0"
            )
        return value

    @property
    def allowed_origins(self) -> list[str]:
        """The CORS origins, as a list, with blanks dropped."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

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
