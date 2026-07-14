import math

from openai import AsyncOpenAI

from app.config import settings
from app.models.content_entries import EMBEDDING_DIMENSION

# NVIDIA NIM again — same platform as clients/llm.py, same free tier, same
# API key. Switched from Voyage AI so there's one provider to manage instead
# of two. nv-embedcode-7b-v1 (also available on this account) was
# considered and ruled out — it's specialized for code retrieval (bug
# search, doc lookup), not general multilingual text. This model instead:
# multilingual across 26 languages including Hindi (the non-negotiable
# requirement per vector-database.md §1), 8192-token context.
client = (
    AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        # See clients/llm.py's client for why this exists — NIM has been
        # observed to hang indefinitely on some calls rather than error.
        timeout=30.0,
        # Same reasoning as clients/llm.py: default max_retries=2 triples a
        # timed-out call's wall-clock (~90s+) for no real benefit against a
        # congested free-tier endpoint. Fail once, fast.
        max_retries=0,
    )
    if settings.nvidia_api_key
    else None
)

EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-1b-v2"


def _truncate_and_normalize(embedding: list[float], dim: int) -> list[float]:
    """This model uses Matryoshka embeddings — natively returns a larger
    vector (2048-dim) trained so that truncating to a shorter prefix and
    re-normalizing still retrieves well. Unlike Voyage's output_dimension
    request parameter, there's no server-side "give me N dims" option here
    per NVIDIA's own model card — the truncation has to happen client-side,
    and re-normalizing after truncating is required, not optional, for
    cosine similarity to behave correctly at the shorter length."""
    truncated = embedding[:dim]
    norm = math.sqrt(sum(x * x for x in truncated))
    if norm == 0:
        return truncated
    return [x / norm for x in truncated]


async def _embed(text: str, input_type: str) -> list[float]:
    if client is None:
        raise RuntimeError("NVIDIA_API_KEY is not configured")

    response = await client.embeddings.create(
        input=[text],
        model=EMBEDDING_MODEL,
        extra_body={"input_type": input_type},  # required by this model — not a standard OpenAI field
    )
    return _truncate_and_normalize(response.data[0].embedding, EMBEDDING_DIMENSION)


async def embed_document(text: str) -> list[float]:
    """For content going *into* the vector store — content_entries rows at
    ingestion time (vector-database.md §4). This model calls it "passage"
    rather than "document", same concept as Voyage's asymmetric embeddings."""
    return await _embed(text, input_type="passage")


async def embed_query(text: str) -> list[float]:
    """For a live message at retrieval time (stage 6). Query and passage
    embeddings are trained to be compared against each other, not
    interchangeable — using the wrong input_type on either side silently
    degrades retrieval quality rather than erroring, so this split matters
    even though both functions look almost identical."""
    return await _embed(text, input_type="query")
