"""Ingests vetted knowledge-base content into content_entries — see
vector-database.md §4's ingestion gate: self-vetted status is eligible here
(unlike redirect_templates/safety_patterns, which require
professional-reviewed and stay empty until that happens). Every entry below
is 'low' or 'medium' risk_tier, self-vetted, sourced from a cited reference
(Burns' cognitive distortion taxonomy, WHO mhGAP) — see each file's own
source note before adding a new one here.

Parses the `## Entry: <key>` / ```yaml frontmatter / body / *Fidelity
note* structure shared by every file in knowledge-base/vetted/, embeds each
entry's body text via embed_document(), and upserts by entry_key so
re-running after an edit updates the row instead of duplicating it.

Run: PYTHONPATH=. uv run python scripts/ingest_content.py
"""

import asyncio
import re
from pathlib import Path

import yaml
from sqlalchemy import select

from app.clients.db import SessionLocal
from app.clients.embeddings import embed_document
from app.models.content_entries import ContentEntry

KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge-base" / "vetted"

# Only files whose whole-file risk tier is 'low'/'medium' and whose entries
# are self-vetted or better belong here — matches the ingestion gate
# (vector-database.md §4). redirect_templates/safety_patterns content
# (high risk) is deliberately never read by this script.
SOURCE_FILES = [
    "thinking-traps.md",
    "grounding-and-psychoeducation.md",
    "life-decision-and-dependency-reflection.md",
    "breathing-invitation.md",
]

# `#{2,3}` — life-decision-and-dependency-reflection.md nests its entries
# one level deeper (### Entry: ...) under "## Life decisions" / "##
# Dependency signals" subheadings; the other files use "## Entry:" directly.
# The trailing annotation line also differs by file: *Fidelity note* for
# source-checked content, *Constraint check* for the README-derived
# life-decision/dependency entries, *Note* for breathing-invitation.md
# (which isn't sourced content at all — see that file's own disclaimer).
ENTRY_PATTERN = re.compile(
    r"#{2,3} Entry: (?P<key>[\w-]+).*?\n"
    r"```yaml\n(?P<frontmatter>.*?)```\n"
    r"(?P<body>.*?)\n\n\*(?:Fidelity note|Constraint check|Note)",
    re.DOTALL,
)


def parse_entries(text: str) -> list[dict]:
    entries = []
    for match in ENTRY_PATTERN.finditer(text):
        frontmatter = yaml.safe_load(match.group("frontmatter"))
        body = match.group("body").strip()
        entries.append(
            {
                "entry_key": match.group("key"),
                "text": body,
                "category": frontmatter["category"],
                "tags": frontmatter.get("tags", []),
                "risk_tier": frontmatter["risk_tier"],
                "status": frontmatter["status"],
                "language": "en",
                "source_citation": frontmatter.get("source"),
                "vetted_by": frontmatter.get("vetted_by"),
                "vetted_date": frontmatter.get("vetted_date"),
            }
        )
    return entries


async def ingest() -> None:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    all_entries = []
    for filename in SOURCE_FILES:
        path = KNOWLEDGE_BASE_DIR / filename
        entries = parse_entries(path.read_text())
        print(f"{filename}: parsed {len(entries)} entries")
        all_entries.extend(entries)

    async with SessionLocal() as db:
        for entry in all_entries:
            embedding = await embed_document(entry["text"])

            existing = await db.execute(select(ContentEntry).where(ContentEntry.entry_key == entry["entry_key"]))
            row = existing.scalar_one_or_none()
            if row is None:
                db.add(ContentEntry(embedding=embedding, **entry))
                print(f"inserted: {entry['entry_key']}")
            else:
                for field, value in entry.items():
                    setattr(row, field, value)
                row.embedding = embedding
                print(f"updated: {entry['entry_key']}")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(ingest())
