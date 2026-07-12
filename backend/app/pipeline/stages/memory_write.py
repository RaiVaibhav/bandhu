from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_turns import ConversationTurn
from app.telemetry.langfuse_setup import traced


@traced("memory.write")
async def write_turn(db: AsyncSession, session_id: UUID, user_content: str, assistant_content: str) -> None:
    """Stage 10 — after Generate produces a reply, insert both halves of the
    turn under the current session. No trimming here: the 14-day cascade
    from user_sessions already bounds total storage, and memory_read's
    windowed query is what bounds how much of it Claude actually sees on any
    given turn. See backend-architecture.md §2.

    Voice turns already arrive as transcribed text by this point — STT runs
    before stage 1, and raw audio is never persisted (§5) — so this function
    doesn't need to know whether the turn originated as voice."""
    db.add_all(
        [
            ConversationTurn(session_id=session_id, role="user", content=user_content),
            ConversationTurn(session_id=session_id, role="assistant", content=assistant_content),
        ]
    )
    await db.commit()
