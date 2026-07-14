from typing import Literal

from opentelemetry import trace
from pydantic import BaseModel, ValidationError

from app.clients.llm import ORCHESTRATOR_MODEL, generate
from app.config import telemetry_config
from app.pipeline.stages.classify import ClassifyResult
from app.pipeline.stages.retrieval import RetrievedChunk
from app.telemetry.langfuse_setup import traced

Tool = Literal["close_the_loop", "offer_suggestion", "notice_thinking_trap"]

ORCHESTRATOR_SYSTEM_PROMPT_TEMPLATE = """You are the judgment step in a companion mental-health check-in app called Bandhu. This is the ONLY place in the whole pipeline that makes a real discretionary call — everything before you was deterministic. Respond with ONLY a JSON object, no other text, no markdown fencing.

Bandhu is companion-first, not suggestion-first. Silence — saying nothing beyond a plain acknowledgment — is the default, expected, correct outcome, even when a tool would be technically available. A tool has to earn its way into the reply; don't reach for one just because you can.

You choose exactly one of these:
{available_tools}

Priority, if more than one would genuinely fit: close_the_loop always outranks offer_suggestion or notice_thinking_trap — never stack them, pick one.

Respond with:
{{"tool": "<one of the above, or null for silence>", "target_entry_key": "<if tool is offer_suggestion: the entry_key of whichever retrieved item actually fits, copied exactly from the list given to you — never invent one. Otherwise null>", "close_the_loop_note": "<if tool is close_the_loop: one short phrase naming what you're referencing from this person's own history — e.g. 'the walk they mentioned trying last week'. Never a direct quote. Otherwise null>"}}

Rules that matter:
- notice_thinking_trap is a quiet, general offer only — do NOT name or hint at which specific thinking pattern you noticed. That naming happens later, only if the person opts in.
- offer_suggestion's target_entry_key must be one of the entry_keys actually given to you below — if none of them genuinely fit what this person said, choose silence instead of forcing one.
- close_the_loop only if there's something real and specific to reference from this person's history below — if there's nothing, choose silence. Never fabricate a memory.
- This is a companion, not a suggestion engine. When in doubt between offering something and staying quiet, stay quiet."""


class OrchestratorDirective(BaseModel):
    """Stage 7's output — see backend-architecture.md §4. `tool: None` is
    silence, the default and most common outcome by design, not a fallback
    for a failed call."""

    tool: Tool | None = None
    target_entry_key: str | None = None
    close_the_loop_note: str | None = None


SILENCE = OrchestratorDirective()


def _build_system_prompt(eligible_for_offer: bool) -> str:
    tools = ['"close_the_loop" — always available, if there\'s something real to reference']
    if eligible_for_offer:
        tools.append('"offer_suggestion" — only because this person is currently eligible (rationed, not every turn)')
        tools.append('"notice_thinking_trap" — only because this person is currently eligible (rationed, not every turn)')
    tools.append("null — silence, the default")
    return ORCHESTRATOR_SYSTEM_PROMPT_TEMPLATE.format(available_tools="\n".join(f"- {t}" for t in tools))


def _build_user_message(
    message_text: str,
    tags: ClassifyResult,
    summary_text: str | None,
    recent_turns: list[dict],
    retrieved_chunks: list[RetrievedChunk],
) -> str:
    chunk_lines = (
        "\n".join(f'- entry_key: "{c.entry_key}" — {c.text}' for c in retrieved_chunks)
        if retrieved_chunks
        else "(none retrieved this turn)"
    )
    buffer_lines = (
        "\n".join(f"{t['role']}: {t['content']}" for t in recent_turns) if recent_turns else "(start of this sitting)"
    )
    return f"""Current message: {message_text}
Classify tags: emotion={tags.emotion}, category={tags.category}, intensity={tags.intensity}

This person's long-term history, for your awareness only, never to be quoted: {summary_text or "No prior context yet."}

Recent conversation this sitting:
{buffer_lines}

Retrieved library content available if offer_suggestion fits:
{chunk_lines}"""


def _validate_directive(raw: OrchestratorDirective, eligible_for_offer: bool, retrieved_chunks: list[RetrievedChunk]) -> OrchestratorDirective:
    """Defense in depth: the system prompt already excludes offer_suggestion/
    notice_thinking_trap when not eligible, and constrains target_entry_key
    to the given list — this re-checks both in code rather than trusting
    the model followed instructions, same posture as classify.py's
    low-confidence fallback. An invalid directive silently degrades to
    silence, never to a guess."""
    if raw.tool in ("offer_suggestion", "notice_thinking_trap") and not eligible_for_offer:
        return SILENCE

    if raw.tool == "offer_suggestion":
        valid_keys = {c.entry_key for c in retrieved_chunks}
        if raw.target_entry_key not in valid_keys:
            return SILENCE

    if raw.tool == "close_the_loop" and not raw.close_the_loop_note:
        return SILENCE

    return raw


@traced("pipeline.orchestrator_judgment")
async def judge(
    message_text: str,
    tags: ClassifyResult,
    summary_text: str | None,
    recent_turns: list[dict],
    eligible_for_offer: bool,
    retrieved_chunks: list[RetrievedChunk],
) -> OrchestratorDirective:
    system_prompt = _build_system_prompt(eligible_for_offer)
    user_message = _build_user_message(message_text, tags, summary_text, recent_turns, retrieved_chunks)

    raw_response = await generate(
        model=ORCHESTRATOR_MODEL,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=300,
    )

    try:
        parsed = OrchestratorDirective.model_validate_json(raw_response)
    except ValidationError:
        parsed = SILENCE

    directive = _validate_directive(parsed, eligible_for_offer, retrieved_chunks)

    span = trace.get_current_span()
    span.set_attribute("orchestrator.tool", directive.tool or "silence")
    if telemetry_config.message_content and directive.target_entry_key:
        span.set_attribute("orchestrator.target_entry_key", directive.target_entry_key)

    return directive
