from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore" because TelemetryConfig below reads the same .env file
    # for its own keys (TELEMETRY_LOG_*) — without this, pydantic-settings'
    # default "forbid" behavior means any real .env file crashes the app on
    # startup the moment it contains a key this class doesn't declare.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Left optional for now — nothing in this milestone touches Supabase or
    # NVIDIA NIM yet, so the app can start with an empty .env. Stages that
    # need these will fail loudly and specifically once we build them,
    # instead of this file guessing or hardcoding a fallback.
    database_url: str | None = None
    # NVIDIA NIM — free-tier, OpenAI-compatible access to hosted open
    # models. Used for both generation (clients/llm.py) and embeddings
    # (clients/embeddings.py) — one key, one provider, instead of a
    # separate Anthropic key for generation and Voyage key for embeddings.
    # See vector-database.md §1.
    nvidia_api_key: str | None = None

    # Langfuse — telemetry. See docs/backend-architecture.md §10 for why
    # Langfuse over the originally-planned Phoenix, and the open item on
    # session_id retention. langfuse_host depends on which region your
    # project was created in — check Settings > Project in the Langfuse
    # dashboard, it shows the exact host for your keys.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Comma-separated allowed origins for CORSMiddleware. Defaults cover
    # local dev (Vite on :5173, `vite preview` on :4173) — production sets
    # this to the deployed frontend's real origin(s) via env var, since a
    # credentialed cookie (bandhu_sid) can't pair with allow_origins=["*"].
    cors_allow_origins: str = "http://localhost:5173,http://localhost:4173"

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


class TelemetryConfig(BaseSettings):
    """Controls what actually leaves the server in a telemetry span, separate
    from whether telemetry is configured at all. Metadata (stage, latency,
    tokens, session_id, errors) always logs — these flags gate raw content
    fields specifically, and default OFF: a mental-health check-in app should
    not ship someone's message text to a third party unless that's a
    deliberate choice, not a forgotten default."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="telemetry_log_", extra="ignore"
    )

    message_content: bool = False
    retrieval_content: bool = False
    prompt_content: bool = False


settings = Settings()
telemetry_config = TelemetryConfig()
