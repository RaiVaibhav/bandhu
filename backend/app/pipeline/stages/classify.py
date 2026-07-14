from typing import Literal

from opentelemetry import trace
from pydantic import BaseModel, ValidationError

from app.clients.llm import CLASSIFY_MODEL, generate
from app.config import telemetry_config
from app.telemetry.langfuse_setup import traced

SpecialCase = Literal["redirect-medical", "redirect-disorder", "redirect-medication", "redirect-document"]
Category = Literal["grounding-technique", "thinking-trap", "life-decision-reflection", "dependency-reflection"]
Intensity = Literal["low", "medium", "high"]

CLASSIFY_SYSTEM_PROMPT = """You read one message from someone checking in on a companion mental-health app and classify it. Respond with ONLY a JSON object, no other text, no markdown fencing.

First check if the message clearly, unambiguously, and primarily falls into one of these special cases — not just adjacent to the topic:
- "redirect-medical": asking whether they have a specific medical condition, or seeking a diagnosis
- "redirect-disorder": asking whether they have a specific mental health disorder (e.g. "do I have depression", "is this bipolar")
- "redirect-medication": asking what medication to take, dosage, or medication questions generally
- "redirect-document": the message is about interpreting a medical document/report

If one applies, respond with exactly (substituting the matching value):
{"special_case": "redirect-medical", "emotion": null, "category": null, "intensity": null, "confidence": "high"}

Otherwise, respond with:
{"special_case": null, "emotion": "<one or two words for emotional tone, e.g. 'anxious', 'sad', 'stressed', 'flat'>", "category": "<one of: grounding-technique, thinking-trap, life-decision-reflection, dependency-reflection — whichever kind of support this message calls for, if any>", "intensity": "<low, medium, or high>", "confidence": "<low or high>"}

Use "confidence": "low" and leave emotion/category/intensity as null if the message is too short, ambiguous, or low-signal to classify honestly (e.g. "idk", a bare emoji, "ok") — never force-fit a message like that into the nearest category just to fill the field."""


class ClassifyResult(BaseModel):
    """Stage 3's output — see backend-architecture.md §4. A `special_case`
    short-circuits straight to the fixed redirect-template branch, skipping
    Retrieval/Orchestrator/Generate entirely. `confidence: "low"` is the
    explicit low-signal path pipeline.html flagged as missing — the
    Orchestrator should treat it as "say nothing forced," not force-fit a
    guess into the nearest category."""

    special_case: SpecialCase | None = None
    emotion: str | None = None
    category: Category | None = None
    intensity: Intensity | None = None
    confidence: Literal["low", "high"] = "high"


LOW_CONFIDENCE_FALLBACK = ClassifyResult(confidence="low")


@traced("pipeline.classify")
async def classify(message_text: str) -> ClassifyResult:
    span = trace.get_current_span()

    raw = await generate(
        model=CLASSIFY_MODEL,
        system=CLASSIFY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message_text}],
        max_tokens=200,
    )

    try:
        result = ClassifyResult.model_validate_json(raw)
    except ValidationError:
        # Malformed JSON or an out-of-schema value — don't force-fit onto
        # the nearest category. Same low-confidence path a genuinely
        # ambiguous message takes, not a crash.
        result = LOW_CONFIDENCE_FALLBACK

    # Metadata (always logs, low sensitivity): whether a special case fired
    # at all, and confidence. The specific tag values are closer to raw
    # content — they reveal real personal state — so those stay behind the
    # same message_content flag as conversation text (app/config.py).
    span.set_attribute("classify.special_case_triggered", result.special_case is not None)
    span.set_attribute("classify.confidence", result.confidence)
    if telemetry_config.message_content:
        span.set_attribute("classify.special_case", result.special_case or "none")
        span.set_attribute("classify.emotion", result.emotion or "none")
        span.set_attribute("classify.category", result.category or "none")
        span.set_attribute("classify.intensity", result.intensity or "none")

    return result
