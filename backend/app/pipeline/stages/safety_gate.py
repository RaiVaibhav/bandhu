from datetime import datetime, timedelta, timezone
from typing import Literal

from opentelemetry import trace
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.safety_patterns import SafetyPattern
from app.telemetry.langfuse_setup import traced

# Starting guess, not validated — see backend-architecture.md Open Items.
# How long a crisis card stays suppressed after it last fired in this
# session. Reuses the same window as the conversation buffer for now,
# purely for consistency, not because it's been reasoned through
# separately.
SUPPRESSION_WINDOW = timedelta(hours=2)

# Most severe first. self-harm and direct are both immediate triggers on
# their own; indirect only reaches here at all once corroborated by a
# direct statement in the buffer (see evaluate_safety below), so it's
# ranked softer even when confirmed.
SEVERITY_PRIORITY = ["self-harm", "direct", "indirect"]

Severity = Literal["self-harm", "direct", "indirect"]


class SafetyGateResult(BaseModel):
    """Stage 2's output — see backend-architecture.md §4. `triggered` is the
    detection result and always reflects a fresh match, every time.
    `should_display` is the separate, later-overridable display decision —
    suppression is a UI choice, never a detection skip (same match still
    runs, and still updates last_crisis_card_shown_at logic, even when the
    card itself doesn't re-render)."""

    triggered: bool
    severity: Severity | None = None
    should_display: bool = False


def _find_matches(text: str, patterns: list[SafetyPattern]) -> set[str]:
    lowered = text.lower()
    return {p.pattern_type for p in patterns if p.pattern.lower() in lowered}


def _most_severe(types: set[str]) -> Severity | None:
    for candidate in SEVERITY_PRIORITY:
        if candidate in types:
            return candidate  # type: ignore[return-value]
    return None


def _outside_suppression_window(last_shown: datetime | None) -> bool:
    if last_shown is None:
        return True
    return datetime.now(timezone.utc) - last_shown > SUPPRESSION_WINDOW


def evaluate_safety(
    message_text: str,
    recent_turns: list[dict],
    patterns: list[SafetyPattern],
    last_crisis_card_shown_at: datetime | None,
) -> SafetyGateResult:
    """The actual matching logic, kept separate from the DB fetch so it's
    directly unit-testable — this is the one stage in the whole pipeline
    where a logic bug is the failure mode that matters most."""
    current_matches = _find_matches(message_text, patterns)

    triggered_types = {t for t in current_matches if t in ("direct", "self-harm")}

    if "indirect" in current_matches:
        # A hedge ("just thinking about it") only counts as a hedge if a
        # direct statement appears earlier in this sitting's buffer — see
        # backend-architecture.md §2/§4. Only the person's own prior
        # messages can supply that corroboration, not Bandhu's replies.
        user_buffer_text = " ".join(t["content"] for t in recent_turns if t["role"] == "user").lower()
        direct_patterns = [p for p in patterns if p.pattern_type == "direct"]
        if any(p.pattern.lower() in user_buffer_text for p in direct_patterns):
            triggered_types.add("indirect")

    triggered = bool(triggered_types)
    severity = _most_severe(triggered_types) if triggered else None
    should_display = triggered and _outside_suppression_window(last_crisis_card_shown_at)

    return SafetyGateResult(triggered=triggered, severity=severity, should_display=should_display)


async def _fetch_active_patterns(db: AsyncSession, language: str) -> list[SafetyPattern]:
    result = await db.execute(
        select(SafetyPattern).where(SafetyPattern.active.is_(True), SafetyPattern.language == language)
    )
    return list(result.scalars().all())


@traced("pipeline.safety_gate")
async def check_safety(
    db: AsyncSession,
    message_text: str,
    recent_turns: list[dict],
    last_crisis_card_shown_at: datetime | None,
    language: str = "en",
) -> SafetyGateResult:
    patterns = await _fetch_active_patterns(db, language)
    result = evaluate_safety(message_text, recent_turns, patterns, last_crisis_card_shown_at)

    span = trace.get_current_span()
    span.set_attribute("safety_gate.triggered", result.triggered)
    span.set_attribute("safety_gate.should_display", result.should_display)
    if result.severity:
        span.set_attribute("safety_gate.severity", result.severity)
    # Deliberately never logs the matched pattern text or message content
    # here, not even behind the message_content flag (app/config.py) that
    # gates general conversation content — the exact words that tripped a
    # crisis-language match are a harder line than ordinary message
    # content, and this stage doesn't need the raw text to be debuggable;
    # triggered/severity/should_display already say what happened.

    return result
