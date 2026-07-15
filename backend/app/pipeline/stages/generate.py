from collections.abc import AsyncIterator

from opentelemetry import trace

from app.clients.llm import GENERATE_MODEL
from app.clients.llm import generate as llm_generate
from app.clients.llm import generate_stream as llm_generate_stream
from app.config import telemetry_config
from app.pipeline.stages.orchestrator_judgment import OrchestratorDirective
from app.pipeline.stages.retrieval import RetrievedChunk
from app.telemetry.langfuse_setup import record_io, traced

# ~60-word cap per pipeline.html — 150 tokens is generous headroom over that
# for English (~1.3 tokens/word), matches the worked example in
# backend-architecture.md §6 exactly rather than deriving a fresh number.
MAX_TOKENS = 150

BANDHU_PERSONA_AND_CONSTRAINTS = """You are Bandhu, a warm companion for mental health check-ins in India — not a therapist, not a diagnostic tool. Write ONE short reply, at most a couple of sentences (~60 words), in plain, warm, specific language — never generic, never clinical-sounding.

Hard constraints, always:
- Never diagnose. Never name a clinical condition or disorder.
- Never recommend a specific course of action ("you should try X") — offering something to consider is fine, prescribing isn't.
- Never recite anything from this person's history as if it were a quote or a data recap ("you said X on Tuesday") — reference it only the way someone who remembers would, softly, in passing, never itemized.
- Acknowledge what was actually just said, first, before anything else — the acknowledgment must be complete and warm on its own, even if nothing else follows. Reflect it back in your own words, not a near-repeat of their own phrasing — find a fresh, specific image or turn of phrase for what they're describing, the way someone really listening would, not a template restating their sentence.
- Use ONLY the specific content handed to you below for any suggestion or reference — never invent a technique, fact, or memory that wasn't given to you."""


def _directive_instruction(directive: OrchestratorDirective, retrieved_chunks: list[RetrievedChunk]) -> str:
    """Translates stage 7's decision into a phrasing instruction. Generate
    never re-decides anything here — it only ever renders whichever branch
    the directive already settled on."""
    if directive.tool is None:
        return (
            "This turn: acknowledgment only — no suggestion, technique, or offer of any kind. "
            "If they're visibly holding something back or trailing off — naming a feeling without "
            'the details, saying "it\'s a lot" or "I don\'t want to get into it" — close with a '
            'short, open invitation to keep going if they want to: "let it out", "I\'m here if you '
            'want to say more", something in that spirit, never a pointed question demanding an '
            "answer, just an open door. Skip it when they've already said their piece and the "
            "acknowledgment reads complete on its own — it's for the moments where more is "
            "clearly sitting unsaid, not a line every reply needs."
        )

    if directive.tool == "close_the_loop":
        return (
            "This turn: after acknowledging, add one short, warm line referencing this, "
            f'naturally — never as a direct quote or a "you said" recap: {directive.close_the_loop_note}'
        )

    if directive.tool == "offer_suggestion":
        chunk = next((c for c in retrieved_chunks if c.entry_key == directive.target_entry_key), None)
        content = chunk.text if chunk else ""
        return (
            "This turn: after acknowledging, offer this once, warmly, only if it fits naturally — "
            f'do not force it if the acknowledgment already feels complete: "{content}"'
        )

    if directive.tool == "notice_thinking_trap":
        return (
            "This turn: after acknowledging, add one quiet, general line noticing that how they're "
            "thinking about this might be worth a second look — a yes/no invitation only. Do NOT "
            "name or describe the specific pattern you noticed; that comes later, only if they opt in."
        )

    if directive.tool == "thinking_trap_followup":
        chunk = next((c for c in retrieved_chunks if c.entry_key == directive.target_entry_key), None)
        content = chunk.text if chunk else ""
        return (
            "This turn is different from your usual one-line acknowledgment — the person just told you "
            f'which thinking pattern actually fits them: "{content}" Go deeper here, not shorter. Warmly '
            "acknowledge that they named it (this takes real self-awareness), weave in what that pattern "
            "actually is in your own words — never just repeat the definition back like a dictionary entry — "
            "and then ask ONE genuine, curious, specific question inviting them to tell you about an actual "
            "recent moment this showed up for them. Sound like a curious companion leaning in, not a "
            "clinician summarizing a diagnosis or a form asking for details. Two to four sentences is fine "
            "here — this is the one turn allowed to run longer than the usual short reply."
        )

    return "This turn: acknowledgment only."  # unreachable given OrchestratorDirective's Literal type


def _build_messages_and_system(
    message_text: str,
    recent_turns: list[dict],
    summary_text: str | None,
    directive: OrchestratorDirective,
    retrieved_chunks: list[RetrievedChunk],
) -> tuple[list[dict], str]:
    """Shared by generate_reply and generate_reply_stream — both need the
    exact same messages/system split, just differ in whether they await one
    completion or iterate a stream of deltas."""
    messages = [{"role": t["role"], "content": t["content"]} for t in recent_turns]
    messages.append({"role": "user", "content": message_text})

    system_prompt = f"""{BANDHU_PERSONA_AND_CONSTRAINTS}

Rolling context on this person — for your own awareness only, never to be recited back to them:
{summary_text or "No prior context yet."}

{_directive_instruction(directive, retrieved_chunks)}"""

    return messages, system_prompt


def _record_generate_span(directive: OrchestratorDirective, message_text: str, response_text: str) -> None:
    span = trace.get_current_span()
    span.set_attribute("generate.tool", directive.tool or "silence")
    span.set_attribute("generate.response_length_chars", len(response_text))
    if telemetry_config.message_content:
        span.set_attribute("generate.response_text", response_text)
        record_io(span, input_data={"message_text": message_text, "directive": directive.tool}, output_data=response_text)


@traced("pipeline.generate")
async def generate_reply(
    message_text: str,
    recent_turns: list[dict],
    summary_text: str | None,
    directive: OrchestratorDirective,
    retrieved_chunks: list[RetrievedChunk],
    max_tokens: int = MAX_TOKENS,
) -> str:
    """Stage 8 — see backend-architecture.md §4/§6. Doesn't decide anything
    new; only phrases whatever stage 7 already decided. system/messages stay
    structurally split, same as §6 — the long-term summary lives only in
    system, never in messages, so it can't come out looking like something
    just said.

    max_tokens defaults to the ~60-word cap every ordinary turn gets, but
    thinking_trap_followup deliberately calls this with a higher ceiling
    (main.py's POST /thinking-trap) — that's the one turn meant to run
    longer than a normal acknowledgment, per its own directive instruction
    below telling the model exactly that."""
    messages, system_prompt = _build_messages_and_system(
        message_text, recent_turns, summary_text, directive, retrieved_chunks
    )

    response_text = await llm_generate(
        model=GENERATE_MODEL,
        system=system_prompt,
        messages=messages,
        max_tokens=max_tokens,
    )

    _record_generate_span(directive, message_text, response_text)
    return response_text


@traced("pipeline.generate_stream")
async def generate_reply_stream(
    message_text: str,
    recent_turns: list[dict],
    summary_text: str | None,
    directive: OrchestratorDirective,
    retrieved_chunks: list[RetrievedChunk],
    max_tokens: int = MAX_TOKENS,
) -> AsyncIterator[str]:
    """Streaming twin of generate_reply — same instruction-building, same
    span attributes recorded at the end, just yields text deltas as they
    arrive instead of returning once. Used by orchestrator.py's
    run_pipeline_stream, which is the only caller that needs deltas rather
    than a single string; every other caller (guardrail_check.py's own
    SILENCE fallback regeneration, /thinking-trap) still wants one
    complete string and should keep using generate_reply."""
    messages, system_prompt = _build_messages_and_system(
        message_text, recent_turns, summary_text, directive, retrieved_chunks
    )

    full_text_parts: list[str] = []
    async for delta in llm_generate_stream(
        model=GENERATE_MODEL, system=system_prompt, messages=messages, max_tokens=max_tokens
    ):
        full_text_parts.append(delta)
        yield delta

    _record_generate_span(directive, message_text, "".join(full_text_parts))
