from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import telemetry_config
from app.pipeline.stages.classify import SpecialCase
from app.models.redirect_templates import RedirectTemplate
from app.telemetry.langfuse_setup import record_io, traced

# Used only when a category has no professional-reviewed row yet — see
# vector-database.md §4: "As of 2026-07-11, none of the four redirect
# templates ... are professional-reviewed", so the ingestion gate correctly
# blocks all four from redirect_templates today (knowledge-base/VETTING.md).
# NOT a substitute for that content — a safe, generic stand-in so the
# pipeline degrades to something honest instead of crashing or improvising
# clinical-adjacent phrasing, until the real templates clear review.
FALLBACK_TEXT = (
    "That's a good question to bring to a doctor or mental health professional directly — "
    "it's not something I can weigh in on here."
)


@traced("pipeline.redirect")
async def get_redirect(db: AsyncSession, category: SpecialCase) -> str:
    """Stage 3's fixed-redirect branch — direct lookup by category, no
    similarity search (pipeline.html/vector-database.md §2): the right
    answer never depends on retrieval. The professional-review ingestion
    gate is what actually enforces content safety here — this stage just
    reads whatever's live in the table, same posture as safety_gate.py
    reading whatever's live in safety_patterns."""
    result = await db.execute(
        select(RedirectTemplate.template_text).where(RedirectTemplate.category == category)
    )
    template_text = result.scalar_one_or_none()

    span = trace.get_current_span()
    span.set_attribute("redirect.category", category)
    span.set_attribute("redirect.template_found", template_text is not None)
    if telemetry_config.message_content:
        span.set_attribute("redirect.response_text", template_text or FALLBACK_TEXT)
        record_io(span, input_data=category, output_data=template_text or FALLBACK_TEXT)

    return template_text or FALLBACK_TEXT
