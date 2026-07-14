from openai import AsyncOpenAI

from app.config import settings

# NVIDIA NIM — OpenAI-compatible endpoint over 100+ hosted open models, free
# tier (no card, ~1000-5000 credits, 40 req/min). Switched to from Anthropic
# since no paid Anthropic key is available; see vector-database.md §1 for
# the full reasoning. Provider-neutral module name on purpose — "claude.py"
# would be actively wrong now that nothing here calls Claude.
client = (
    AsyncOpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=settings.nvidia_api_key)
    if settings.nvidia_api_key
    else None
)

# Model tiers — see vector-database.md §1 for the reasoning behind each
# choice. Reserve the largest model for the two stages that actually need
# judgment (Orchestrator, sampled Evaluator); everything else is a small,
# bounded task that doesn't need it. Llama 3.1 wasn't actually available on
# this account/region — these are the models confirmed available instead
# (2026-07-14), picked by active-parameter size within each family (NVIDIA
# NIM's MoE models are named "<total>b-a<active>b" — e.g. 80b-a3b means 80B
# total, 3B active) rather than sticking to a single model family.
CLASSIFY_MODEL = "qwen/qwen3-next-80b-a3b-instruct"  # smallest active-param count of what's available
GENERATE_MODEL = "qwen/qwen3-next-80b-a3b-instruct"
SUMMARIZER_MODEL = "qwen/qwen3.5-122b-a10b"  # mid-sized
ORCHESTRATOR_MODEL = "deepseek-ai/deepseek-v4-pro"  # DeepSeek's flagship reasoning tier
EVALUATOR_MODEL = "deepseek-ai/deepseek-v4-pro"


async def generate(model: str, system: str, messages: list[dict], max_tokens: int = 150) -> str:
    """The one LLM call shape every pipeline stage needs. `system` is kept
    as a separate parameter here — not because the underlying API has a
    top-level system slot (OpenAI-shaped APIs don't; it becomes the first
    entry in `messages` with role="system") — but because keeping it
    separate at this function's boundary is what stops a caller from ever
    concatenating the long-term summary into the same string as the actual
    conversation. See backend-architecture.md §6: the guarantee that the
    summary/directive can't surface as if it were said in the chat comes
    from the `system` role being structurally distinct from `user`/
    `assistant`, not from its position in the payload — that distinction
    survives the provider swap intact.

    No manual span here — OpenAIInstrumentor (telemetry/langfuse_setup.py)
    auto-instruments every call made through this client already."""
    if client is None:
        raise RuntimeError("NVIDIA_API_KEY is not configured")

    full_messages = [{"role": "system", "content": system}, *messages]

    response = await client.chat.completions.create(
        model=model,
        messages=full_messages,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content
