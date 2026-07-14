from openai import AsyncOpenAI

from app.config import settings

# NVIDIA NIM — OpenAI-compatible endpoint over 100+ hosted open models, free
# tier (no card, ~1000-5000 credits, 40 req/min). Switched to from Anthropic
# since no paid Anthropic key is available; see vector-database.md §1 for
# the full reasoning. Provider-neutral module name on purpose — "claude.py"
# would be actively wrong now that nothing here calls Claude.
client = (
    AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        # A hung upstream call used to hang the entire request indefinitely
        # (discovered 2026-07-14 wiring up the first real end-to-end test:
        # the originally-configured qwen3-next-80b-a3b-instruct and
        # deepseek-v4-pro model IDs never respond at all — not an error,
        # not a timeout, just silence — and blocked a `POST /message` call,
        # graceful uvicorn reload, and everything downstream of it forever).
        # 30s is generous for this pipeline's largest single call
        # (Orchestrator, max_tokens=300) while still failing fast enough
        # that a real request doesn't hang the person staring at it.
        timeout=30.0,
        # The openai SDK retries timeouts by default (max_retries=2 → 3
        # attempts total) — discovered 2026-07-14 when a real request took
        # 112s to fail instead of the ~30s the timeout above implies: 3
        # attempts x ~37s each. A slow/congested NVIDIA free-tier response
        # rarely recovers on an immediate retry, so retrying just triples
        # the person's wait for the same eventual failure. Fail once, fast.
        max_retries=0,
    )
    if settings.nvidia_api_key
    else None
)

# Model tiers — see vector-database.md §1 for the reasoning behind each
# choice. Reserve the largest reliable model for the two stages that
# actually need judgment (Orchestrator, sampled Evaluator); everything else
# is a small, bounded task that doesn't need it.
#
# Verified by direct API call on 2026-07-14, not assumed: the previously
# configured qwen3-next-80b-a3b-instruct, qwen3.5-122b-a10b, and
# deepseek-v4-pro all hang indefinitely on this account — no error, no
# response, confirmed via raw curl (bypassing this codebase entirely) so
# it isn't a bug in generate() below. meta/llama-3.1-70b-instruct is also
# available but intermittently hung in the same testing (3/4 successes) —
# not reliable enough to build the Orchestrator's judgment call on.
# nvidia/llama-3.3-nemotron-super-49b-v1 (NVIDIA's own reasoning-tuned
# Nemotron line) and meta/llama-3.1-8b-instruct were both reliable across
# repeated calls. If NVIDIA's catalog changes again, re-verify with a raw
# curl + a hard timeout before trusting a model id — see this file's git
# history for the exact commands used.
#
# ORCHESTRATOR_MODEL moved off nemotron-49b to the fast model 2026-07-14:
# reasoning-tuned models trade consistent latency for judgment quality, and
# under a realistic (not toy) Orchestrator prompt, nemotron-49b measured
# 2-26s across 5 identical calls — occasionally exceeding the client's 30s
# timeout outright, which is squarely in the synchronous /message request
# path a person is actively waiting on. SUMMARIZER_MODEL/EVALUATOR_MODEL
# stay on nemotron-49b deliberately: neither is in that synchronous path
# (Summarizer runs nightly, Evaluator runs async via BackgroundTasks after
# the response already went out), so their latency doesn't cost the person
# anything and the better judgment quality is worth keeping there. Explicit
# trade-off, not yet validated against real conversation quality either
# way — see vector-database.md §5's open item on this.
CLASSIFY_MODEL = "meta/llama-3.1-8b-instruct"
GENERATE_MODEL = "meta/llama-3.1-8b-instruct"
SUMMARIZER_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"
ORCHESTRATOR_MODEL = "meta/llama-3.1-8b-instruct"
EVALUATOR_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"


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
