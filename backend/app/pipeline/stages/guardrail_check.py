import re

from opentelemetry import trace

from app.pipeline.stages.generate import generate_reply
from app.pipeline.stages.orchestrator_judgment import SILENCE
from app.telemetry.langfuse_setup import traced


class Violation:
    DIAGNOSIS = "diagnosis"
    RECOMMENDATION = "recommendation"
    DEPENDENCY_REINFORCEMENT = "dependency_reinforcement"


# Starting rule set, not exhaustive — resolves pipeline.html's own open item
# ("needs real rejection criteria, not just a principle. Needs example
# pass/fail pairs before it's testable") but should be revisited once real
# Generate output is observed, same posture as the crisis-language starter
# list. Deliberately keyword/regex-based, not a second Claude call: this
# needs to be exact and auditable, not another probabilistic step with its
# own failure surface.

# Unambiguous clinical labels — a companion app has no legitimate reason to
# ever say these, so a bare match is safe (unlike "depression"/"anxiety"
# alone, which are also just ordinary feeling-words Bandhu uses constantly).
DIAGNOSTIC_LABEL_TERMS = [
    "bipolar",
    "ptsd",
    "ocd",
    "schizophrenia",
    "adhd",
    "borderline personality",
    "clinical depression",
    "major depressive disorder",
    "generalized anxiety disorder",
    "anxiety disorder",
]

# "depression"/"anxiety" specifically applied AS A DIAGNOSIS to this
# person — not the bare words, which are normal companion vocabulary.
DIAGNOSTIC_APPLICATION_PATTERNS = [
    r"\byou have depression\b",
    r"\byou're depressed\b",
    r"\byou are depressed\b",
    r"\byou have anxiety\b",
    r"\bsounds like depression\b",
    r"\bsounds like anxiety\b",
    r"\bthis is depression\b",
    r"\bthis is anxiety\b",
]

# Negative lookaheads on "should"/"must" specifically because "you
# shouldn't"/"you must not" are common, benign reassurance phrasing
# ("you shouldn't feel guilty") that a naive substring match would
# wrongly flag as a recommendation.
RECOMMENDATION_PATTERNS = [
    r"\byou should\b(?!n['’]?t)",
    r"\byou need to\b",
    r"\byou must\b(?!\s*not)",
    r"\bi recommend\b",
    r"\bi suggest you\b",
    r"\bthe best thing to do is\b",
    r"\bmake sure you\b",
]

DEPENDENCY_REINFORCEMENT_PATTERNS = [
    r"\bonly one who\b",
    r"\bonly person who\b",
    r"\balways here no matter what\b",
    r"\bdon't need anyone else\b",
    r"\bjust need me\b",
]


def check_violations(text: str) -> str | None:
    """Public per stage — orchestrator.py's streaming path (stage 8 stream)
    calls this incrementally on the accumulating buffer as tokens arrive, as
    well as check_and_fallback below calling it once on the complete text."""
    lowered = text.lower()

    if any(term in lowered for term in DIAGNOSTIC_LABEL_TERMS):
        return Violation.DIAGNOSIS
    if any(re.search(p, lowered) for p in DIAGNOSTIC_APPLICATION_PATTERNS):
        return Violation.DIAGNOSIS

    if any(re.search(p, lowered) for p in RECOMMENDATION_PATTERNS):
        return Violation.RECOMMENDATION

    if any(re.search(p, lowered) for p in DEPENDENCY_REINFORCEMENT_PATTERNS):
        return Violation.DEPENDENCY_REINFORCEMENT

    return None


@traced("pipeline.guardrail_check")
async def check_and_fallback(
    response_text: str,
    message_text: str,
    recent_turns: list[dict],
    summary_text: str | None,
) -> str:
    """Stage 9 — see backend-architecture.md §4. On failure, falls back to
    a plain acknowledgment-only reply rather than a separate hardcoded
    string — reusing Generate's own silence path, per pipeline.html:
    "Guardrail fail → acknowledgment only, no optional line, logged for
    review." The violation type is always logged (never the response text
    itself — see telemetry content-control design in langfuse_setup.py),
    which is exactly the review trail that line calls for."""
    violation = check_violations(response_text)

    span = trace.get_current_span()
    span.set_attribute("guardrail.passed", violation is None)
    if violation:
        span.set_attribute("guardrail.violation_type", violation)

    if violation is None:
        return response_text

    return await generate_reply(message_text, recent_turns, summary_text, SILENCE, [])
