from typing import Literal

from opentelemetry import trace
from pydantic import BaseModel

from app.config import telemetry_config
from app.telemetry.langfuse_setup import record_io, traced

InputMode = Literal["text", "voice"]

# Unicode block for Devanagari script (U+0900–U+097F) — covers Hindi typed
# in its native script on a phone's Hindi keyboard.
_DEVANAGARI_RANGE = ("ऀ", "ॿ")


class NormalizedMessage(BaseModel):
    """Stage 1's output — see backend-architecture.md §4. `input_mode` is
    carried through to user_checkins for analytics; nothing downstream
    branches on it except the response end (voice out, §5)."""

    text: str
    language: str
    media_type: Literal["text"] = "text"
    input_mode: InputMode = "text"


def detect_language(text: str) -> str:
    """Starting implementation, not validated — same posture as every other
    unvalidated number/heuristic in this codebase (backend-architecture.md
    §14). Flags 'hi' only when Devanagari-script characters are present.

    Known real gap: this does NOT detect Hindi typed in Latin script
    ("Hinglish" — e.g. pipeline.html's own stress-test example, "aaj bahut
    thak gaya yaar"), which is common on Indian keyboards and is exactly the
    case `vector-database.md`'s embedding-provider choice was made to
    handle well. Script detection can't see that at all — a real fix needs
    either a proper code-switching detector or a cheap LLM call, and
    picking one is future work, not guessed here."""
    if any(_DEVANAGARI_RANGE[0] <= ch <= _DEVANAGARI_RANGE[1] for ch in text):
        return "hi"
    return "en"


@traced("pipeline.ingest")
async def ingest(raw_text: str | None, *, input_mode: InputMode = "text", media_type: Literal["text", "image"] = "text") -> NormalizedMessage:
    """Stage 1 — see backend-architecture.md §4. Text only for now: STT and
    TTS providers are explicitly unresolved (§1/§14), and image ingest needs
    a medical-document check to run before anything else touches the image
    (pipeline.html open item, "blocks build") — neither is guessed at here,
    both raise clearly instead of silently behaving as if they were built."""
    if input_mode == "voice":
        raise NotImplementedError(
            "Voice input needs an STT provider — not yet chosen. See backend-architecture.md §1/§14."
        )
    if media_type == "image":
        raise NotImplementedError(
            "Image ingest needs a medical-document check before anything else touches it — not yet built. "
            "See pipeline.html open items."
        )

    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Empty message text")

    language = detect_language(text)

    span = trace.get_current_span()
    span.set_attribute("ingest.language", language)
    span.set_attribute("ingest.input_mode", input_mode)
    if telemetry_config.message_content:
        span.set_attribute("ingest.text", text)
        record_io(span, input_data=raw_text, output_data={"text": text, "language": language})

    return NormalizedMessage(text=text, language=language, media_type="text", input_mode=input_mode)
