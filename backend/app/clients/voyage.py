import voyageai

from app.config import settings
from app.models.content_entries import EMBEDDING_DIMENSION

client = voyageai.AsyncClient(api_key=settings.voyage_api_key) if settings.voyage_api_key else None

# voyage-4 is Voyage's current general-purpose/multilingual model — needed
# for Hindi/Hinglish per vector-database.md §1. output_dimension pinned to
# match content_entries.embedding's column size exactly, rather than
# trusting the model's default.
EMBEDDING_MODEL = "voyage-4"


async def _embed(text: str, input_type: str) -> list[float]:
    if client is None:
        raise RuntimeError("VOYAGE_API_KEY is not configured")

    result = await client.embed(
        texts=[text],
        model=EMBEDDING_MODEL,
        input_type=input_type,
        output_dimension=EMBEDDING_DIMENSION,
    )
    return result.embeddings[0]


async def embed_document(text: str) -> list[float]:
    """For content going *into* the vector store — content_entries rows at
    ingestion time (vector-database.md §4)."""
    return await _embed(text, input_type="document")


async def embed_query(text: str) -> list[float]:
    """For a live message at retrieval time (stage 6). Voyage's
    document/query asymmetric embeddings are trained to be compared against
    each other, not interchangeable — using the wrong input_type on either
    side silently degrades retrieval quality rather than erroring, so this
    split matters even though both functions look almost identical."""
    return await _embed(text, input_type="query")
