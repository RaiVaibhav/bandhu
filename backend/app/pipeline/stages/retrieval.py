from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embeddings import embed_query
from app.config import telemetry_config
from app.models.content_entries import ContentEntry
from app.telemetry.langfuse_setup import traced

# Structural guarantee, not just an application convention: high-risk
# content is never reachable by similarity search, only 'low'/'medium'.
# See vector-database.md §2/§3 — content_entries also has a DB-level CHECK
# (no_high_risk_embedding) backing this up a second way.
RETRIEVABLE_RISK_TIERS = ("low", "medium")
RESULT_LIMIT = 3


class RetrievedChunk:
    """Plain data holder for one retrieved entry — not a Pydantic model since
    this never crosses a request boundary as JSON, just passed stage-to-stage
    in-process to the Orchestrator (stage 7)."""

    __slots__ = ("entry_key", "text", "category", "tags")

    def __init__(self, entry_key: str, text: str, category: str, tags: list[str]):
        self.entry_key = entry_key
        self.text = text
        self.category = category
        self.tags = tags

    def __repr__(self) -> str:
        return f"RetrievedChunk({self.entry_key!r})"


@traced("pipeline.retrieval")
async def retrieve(
    db: AsyncSession,
    message_text: str,
    categories: list[str],
    language: str = "en",
) -> list[RetrievedChunk]:
    """Stage 6 — see backend-architecture.md §4 / vector-database.md §3.
    Deliberately takes the current message only, never the conversation
    buffer, so search stays anchored to what was just said rather than
    drifting toward whatever the last few turns happened to be about.
    Metadata filter (category, language, risk_tier) runs before the
    similarity ORDER BY — shrinks the candidate set before the more
    expensive vector comparison, not after."""
    query_embedding = await embed_query(message_text)

    result = await db.execute(
        select(ContentEntry)
        .where(
            ContentEntry.category.in_(categories),
            ContentEntry.language == language,
            ContentEntry.risk_tier.in_(RETRIEVABLE_RISK_TIERS),
        )
        .order_by(ContentEntry.embedding.cosine_distance(query_embedding))
        .limit(RESULT_LIMIT)
    )
    rows = result.scalars().all()
    chunks = [RetrievedChunk(r.entry_key, r.text, r.category, r.tags) for r in rows]

    span = trace.get_current_span()
    span.set_attribute("retrieval.result_count", len(chunks))
    if telemetry_config.retrieval_content:
        span.set_attribute("retrieval.entry_keys", [c.entry_key for c in chunks])

    return chunks
