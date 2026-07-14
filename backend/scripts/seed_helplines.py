"""Seeds the real, dial-confirmed helpline numbers from
knowledge-base/safety/helpline-directory.md (verified 2026-07-13).

This is the one high-risk table that isn't gated by professional review —
see helplines.py's own docstring: verified_at is a live phone-verification
fact, not a clinical-content review. Safe to seed for real, unlike
safety_patterns/redirect_templates, which stay empty until that review
happens (vector-database.md §4).

Run once per fresh database: `uv run python scripts/seed_helplines.py`
Safe to re-run — upserts by (org_name, phone_number).
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.clients.db import SessionLocal
from app.models.helplines import Helpline

VERIFIED_AT = datetime(2026, 7, 13, tzinfo=timezone.utc)

HELPLINES = [
    # Both numbers dial-confirmed live 2026-07-13 — keep both, don't drop either.
    {"org_name": "Vandrevala Foundation", "phone_number": "1860-266-2345", "hours": None, "audience": "general"},
    {"org_name": "Vandrevala Foundation", "phone_number": "1800-233-3330", "hours": None, "audience": "general"},
    # Dial-confirmed live; hours NOT confirmed — don't assert a specific window as fact.
    {"org_name": "iCall (TISS)", "phone_number": "9152987821", "hours": None, "audience": "general"},
    # Dial-confirmed live; commonly cited 24x7 but not independently checked.
    {"org_name": "KIRAN", "phone_number": "1800-599-0019", "hours": None, "audience": "general"},
]


async def seed() -> None:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    async with SessionLocal() as db:
        for row in HELPLINES:
            existing = await db.execute(
                select(Helpline).where(
                    Helpline.org_name == row["org_name"],
                    Helpline.phone_number == row["phone_number"],
                )
            )
            match = existing.scalar_one_or_none()
            if match is None:
                db.add(Helpline(verified_at=VERIFIED_AT, **row))
                print(f"inserted: {row['org_name']} {row['phone_number']}")
            else:
                match.verified_at = VERIFIED_AT
                print(f"already present, refreshed verified_at: {row['org_name']} {row['phone_number']}")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
