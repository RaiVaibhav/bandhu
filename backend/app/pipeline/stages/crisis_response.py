from opentelemetry import trace
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import telemetry_config
from app.models.helplines import Helpline
from app.telemetry.langfuse_setup import traced

# Fixed template text — not knowledge-base content (no clinical claim, no
# retrieval), so it lives here as a constant rather than in redirect_templates
# (which is reserved for the 4 special-case categories, vector-database.md
# §2). Deliberately says nothing about the person's specific situation —
# see backend-architecture.md §4 stage 2 and pipeline.html's crisis branch.
CRISIS_CARD_TEXT = (
    "I'm really glad you told me. What you're feeling matters, and you don't have to carry it "
    "alone right now — please reach out to one of these, they're free and someone will actually pick up:"
)

# Shown instead of the full card when should_display is False (a crisis
# card already fired recently in this session) — detection still
# short-circuits the pipeline every time (see orchestrator.py), only the
# rendered content differs. Never implies the situation is resolved.
SUPPRESSED_CARD_TEXT = (
    "I'm still here with you. If things feel like too much again, the numbers from before are "
    "still there whenever you need them."
)


class CrisisResponse(BaseModel):
    """Stage 2's branch output — see backend-architecture.md §4/§2.
    `card_shown` reflects the suppression decision only; `helplines` is
    always empty when suppressed, never a re-render of the same list."""

    response_text: str
    helplines: list[dict]
    card_shown: bool


def _format_helpline(h: Helpline) -> dict:
    return {"org_name": h.org_name, "phone_number": h.phone_number, "hours": h.hours}


@traced("pipeline.crisis_response")
async def build_crisis_response(db: AsyncSession, should_display: bool, audience: str = "general") -> CrisisResponse:
    """Only ever serves a helpline row with a real `verified_at` — an
    unverified number is worse than no number at the one moment this
    actually matters (helplines.py's own guarantee, enforced here since the
    schema itself can't). `audience` defaults to 'general' — the minor/
    age-unknown session flag is still an open policy decision
    (backend-architecture.md §14), not resolved by this stage."""
    result = await db.execute(
        select(Helpline)
        .where(Helpline.audience == audience, Helpline.verified_at.isnot(None))
        .order_by(Helpline.org_name)
    )
    helplines = [_format_helpline(h) for h in result.scalars().all()]

    span = trace.get_current_span()
    span.set_attribute("crisis_response.card_shown", should_display)
    span.set_attribute("crisis_response.verified_helpline_count", len(helplines))
    if telemetry_config.message_content:
        span.set_attribute("crisis_response.orgs", [h["org_name"] for h in helplines])

    if not should_display:
        return CrisisResponse(response_text=SUPPRESSED_CARD_TEXT, helplines=[], card_shown=False)

    return CrisisResponse(response_text=CRISIS_CARD_TEXT, helplines=helplines, card_shown=True)
