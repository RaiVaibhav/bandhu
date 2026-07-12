from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Left optional for now — nothing in this milestone touches Supabase or
    # Claude yet, so the app can start with an empty .env. Stages that need
    # these will fail loudly and specifically once we build them, instead of
    # this file guessing or hardcoding a fallback.
    database_url: str | None = None
    anthropic_api_key: str | None = None
    voyage_api_key: str | None = None

    # Langfuse — telemetry. See docs/backend-architecture.md §10 for why
    # Langfuse over the originally-planned Phoenix, and the open item on
    # session_id retention. langfuse_host depends on which region your
    # project was created in — check Settings > Project in the Langfuse
    # dashboard, it shows the exact host for your keys.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"


class TelemetryConfig(BaseSettings):
    """Controls what actually leaves the server in a telemetry span, separate
    from whether telemetry is configured at all. Metadata (stage, latency,
    tokens, session_id, errors) always logs — these flags gate raw content
    fields specifically, and default OFF: a mental-health check-in app should
    not ship someone's message text to a third party unless that's a
    deliberate choice, not a forgotten default."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="telemetry_log_")

    message_content: bool = False
    retrieval_content: bool = False
    prompt_content: bool = False


settings = Settings()
telemetry_config = TelemetryConfig()
