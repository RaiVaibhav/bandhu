from anthropic import AsyncAnthropic

from app.config import settings

client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

# Model tiers — see vector-database.md §1 for the reasoning behind each
# choice. Reserve the smart/expensive tier for the two stages that actually
# need judgment (Orchestrator, sampled Evaluator); everything else is a
# small, bounded task that doesn't need it.
CLASSIFY_MODEL = "claude-haiku-4-5"
GENERATE_MODEL = "claude-haiku-4-5"
ORCHESTRATOR_MODEL = "claude-opus-4-8"
SUMMARIZER_MODEL = "claude-sonnet-5"
EVALUATOR_MODEL = "claude-opus-4-8"


async def generate(model: str, system: str, messages: list[dict], max_tokens: int = 150) -> str:
    """The one Claude call shape every pipeline stage needs — system and
    messages passed separately, never concatenated into one prompt string.
    See backend-architecture.md §6 for why that split is structural, not
    stylistic: it's what makes the long-term summary and Orchestrator
    directive incapable of surfacing as if they were said in the chat.

    No manual span here — AnthropicInstrumentor (telemetry/langfuse_setup.py)
    auto-instruments every call made through this client already."""
    if client is None:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text
