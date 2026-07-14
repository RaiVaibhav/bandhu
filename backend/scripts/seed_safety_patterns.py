"""LOCAL TESTING ONLY — seeds the DRAFT, SELF-VETTED crisis-language list
from knowledge-base/safety/crisis-language-patterns.md into safety_patterns.

DO NOT run this against any shared or deployed database. This list is
explicitly NOT professional-reviewed — the file itself says "this is a
starting point for a professional to react to, edit, and extend — not a
list to wire into the safety gate as-is." The ingestion gate
(vector-database.md §4) correctly blocks this content from normal
ingestion for exactly that reason; this script is a deliberate, logged
bypass of that gate, solely so the founder can exercise the real Crisis
Support flow locally before real review happens. If you're reading this
and you're not doing exactly that, don't run it.

Only pulls the literal quote-marked phrases from the "Direct statements",
"Indirect / hedged statements", and "Self-harm" sections — the
"Behavioral/contextual signals" section is explicitly flagged in the source
as not keyword-matchable and is skipped entirely, not approximated.

Run: PYTHONPATH=. uv run python scripts/seed_safety_patterns.py
Safe to re-run — upserts by (pattern, pattern_type).
"""

import asyncio

from sqlalchemy import select

from app.clients.db import SessionLocal
from app.models.safety_patterns import SafetyPattern

STATUS = "self-vetted"

# Copied verbatim from knowledge-base/safety/crisis-language-patterns.md —
# not reworded, not expanded. Notably does NOT include "feel like dying" or
# other phrasings outside this exact list; the source file's own matching
# is plain substring, and coverage gaps like that are exactly what
# professional review is for, not something to patch here.
PATTERNS = [
    # Direct statements
    ("want to die", "direct"),
    ("wish i was dead", "direct"),
    ("wish i wasn't here", "direct"),
    ("don't want to be here anymore", "direct"),
    ("don't want to exist", "direct"),
    ("want to end it", "direct"),
    ("end it all", "direct"),
    ("end my life", "direct"),
    ("kill myself", "direct"),
    ("killing myself", "direct"),
    ("no reason to live", "direct"),
    ("nothing to live for", "direct"),
    ("better off dead", "direct"),
    ("everyone would be better off without me", "direct"),
    ("can't go on", "direct"),
    ("can't do this anymore", "direct"),
    ("planning to hurt myself", "direct"),
    ("have a plan", "direct"),
    # Indirect / hedged statements
    ("just thinking about it", "indirect"),
    ("wouldn't actually do anything, but", "indirect"),
    ("sometimes i think about not being here", "indirect"),
    ("what's the point of any of this", "indirect"),
    ("i'm just tired of everything", "indirect"),
    # Self-harm
    ("hurt myself", "self-harm"),
    ("hurting myself", "self-harm"),
    ("cut myself", "self-harm"),
    ("cutting", "self-harm"),
]


async def seed() -> None:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    async with SessionLocal() as db:
        for pattern, pattern_type in PATTERNS:
            existing = await db.execute(
                select(SafetyPattern).where(
                    SafetyPattern.pattern == pattern, SafetyPattern.pattern_type == pattern_type
                )
            )
            match = existing.scalar_one_or_none()
            if match is None:
                db.add(SafetyPattern(pattern=pattern, pattern_type=pattern_type, status=STATUS, active=True))
                print(f"inserted: [{pattern_type}] {pattern!r}")
            else:
                print(f"already present: [{pattern_type}] {pattern!r}")
        await db.commit()

    print(
        "\nLOCAL TESTING ONLY — this data is self-vetted, not professional-reviewed. "
        "Do not deploy a database seeded with this script."
    )


if __name__ == "__main__":
    asyncio.run(seed())
