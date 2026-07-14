import random
from uuid import UUID

from opentelemetry import trace
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.llm import EVALUATOR_MODEL, generate
from app.config import telemetry_config
from app.models.evaluator_scores import EvaluatorScore
from app.telemetry.langfuse_setup import traced

# 5-10% of responses, per pipeline.html stage 12. Starting guess picked from
# the middle of that range, not validated — same posture as every other
# unvalidated number in this codebase (backend-architecture.md §14).
SAMPLE_RATE = 0.075

EVALUATOR_SYSTEM_PROMPT = """You score one reply from a companion mental-health check-in app called Bandhu, against the spirit of the MITI (Motivational Interviewing Treatment Integrity) coding manual. This is an async quality check, run independently of the live conversation — the person never sees this score, and it never changes what already happened. Respond with ONLY a JSON object, no other text, no markdown fencing.

Score each MITI-inspired dimension 1-5 (5 is best):
- cultivating_change_talk: does the reply invite the person's own reasons/motivation, rather than supplying them
- softening_sustain_talk: does the reply avoid arguing or pushing back against where the person currently is
- partnership: does the reply read as alongside the person, not above or apart from them
- empathy: does the reply reflect genuine understanding of what was actually said

Separately, score whether the acknowledgment reads as complete and warm on its own, independent of whatever else (if anything) was offered.

Respond with:
{"miti_scores": {"cultivating_change_talk": <1-5>, "softening_sustain_talk": <1-5>, "partnership": <1-5>, "empathy": <1-5>}, "acknowledgment_complete": <true or false>}"""


class EvaluatorResult(BaseModel):
    miti_scores: dict[str, int]
    acknowledgment_complete: bool


def should_sample() -> bool:
    """Caller decides whether to spend an EVALUATOR_MODEL call at all —
    kept as its own function, not folded into evaluate_reply, so the
    sampling decision is independently visible and testable."""
    return random.random() < SAMPLE_RATE


@traced("pipeline.evaluator")
async def evaluate_reply(
    db: AsyncSession, checkin_id: UUID, message_text: str, response_text: str
) -> EvaluatorResult | None:
    """Stage 12 — async, sampled, never affects what the person sees (see
    backend-architecture.md §4/§10 — this is evaluation, not tracing;
    don't conflate the two). Returns None on a malformed model response
    rather than writing a garbage row — same defense-in-depth posture as
    classify.py/orchestrator_judgment.py."""
    raw = await generate(
        model=EVALUATOR_MODEL,
        system=EVALUATOR_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Person's message: {message_text}\n\nBandhu's reply: {response_text}",
            }
        ],
        max_tokens=200,
    )

    try:
        result = EvaluatorResult.model_validate_json(raw)
    except ValidationError:
        return None

    db.add(
        EvaluatorScore(
            checkin_id=checkin_id,
            miti_scores=result.miti_scores,
            acknowledgment_complete=result.acknowledgment_complete,
        )
    )
    await db.commit()

    span = trace.get_current_span()
    span.set_attribute("evaluator.acknowledgment_complete", result.acknowledgment_complete)
    if telemetry_config.message_content:
        span.set_attribute("evaluator.miti_scores", str(result.miti_scores))

    return result
