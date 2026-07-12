# Vector database design

Companion to `docs/rag-components.html` (what each component is and which pipeline stage calls it) and `docs/pipeline.html` (the 12-stage flow). This doc is the layer underneath both: actual schema, actual queries, actual technology choices.

---

## 1. Technology choices

### One database: Supabase (PostgreSQL + pgvector)

This has changed twice already in this doc's history, worth being upfront about why, since the reasoning each time is more useful than just the final answer:

1. **First pass**: one Postgres server, two logical databases (content vs. user data) — split for clean deletion and blast-radius isolation.
2. **Second pass**: Weaviate for content, Postgres for user data — split by technology instead, since Weaviate's built-in hybrid (vector + BM25) search is a real capability pgvector doesn't hand you for free.
3. **This pass, final**: **back to one Postgres database, on Supabase specifically** — because the actual constraint driving the decision is cost, not capability, and on a free-tier single-instance deployment, several of the earlier arguments don't hold the way they did in the abstract:
   - **Blast-radius isolation was never free to begin with.** "Separate connection pools" only means something if you're actually running separate infrastructure. A single free-tier Supabase project gives you one shared connection pooler no matter how many databases or schemas you organize tables into — so the isolation argument from pass 1 was true in principle but not achievable at $0, and shouldn't be oversold as a real guarantee here.
   - **Weaviate's hybrid-search advantage turned out to be closable at zero cost anyway.** Postgres already has full-text search (`tsvector`/`ts_rank`) alongside `pgvector`'s vector search — combining them yourself via Reciprocal Rank Fusion is more SQL to write than Weaviate's one-line `hybrid()` call, but it's a documented pattern (Supabase publishes a reference implementation), not something invented from scratch. See §3.
   - **Weaviate itself isn't free to keep running.** Its free cloud tier is a time-limited sandbox, not a persistent free plan — self-hosting avoids that but adds a service to operate. Neither is compatible with "don't want to pay for anything."

**Net result**: one Supabase Postgres database, `pgvector` extension enabled, holding both the content library and per-user data. Tables are still organized with clear naming (and could live in separate schemas purely for readability), but that's an organizational choice now, not an isolation boundary — the free tier doesn't give you real isolation to lean on either way.

**Why Supabase specifically, over Neon or a bare self-hosted Postgres**: a genuinely persistent free tier (not a sandbox), `pgvector` supported out of the box, and a managed dashboard that's friendlier for a first backend project than raw `psql` against a self-hosted instance. Neon is a reasonable alternative with a similar free tier — either is fine; Supabase is the one actually being used here per your call.

### Object storage — Supabase Storage, for the one kind of data that genuinely doesn't belong in Postgres

Images the person creates (see §2's `user_creations` table) are binary files, not rows — putting them directly in Postgres works but isn't what a relational database is built for. Supabase bundles S3-compatible object storage in the same free project already being used for everything else, so this isn't a new account or a new cost, just a different piece of the same platform. Poems are plain text and don't need this — they go straight into a column, same as any other text. The same bucket also holds the curated audio files for **Listen** (§2's `audio_tracks` table) — a different, non-personal use of the same storage mechanism, covered separately below since it's Bandhu-provided content, not something the person made (see `backend-architecture.md` §13 for why these turned out to be two different features, not one).

### Embedding provider — not Anthropic

**Important, and worth stating plainly: Claude does not have a native embeddings API.** The Messages API, tool use, batches, and files are all Claude does — embeddings are a different capability from a different kind of model entirely (a vector encoder, not a generative model). Anthropic's own documented recommendation for this is **Voyage AI**, and specifically a model in their multilingual line — which matters here more than usual, since a generic English-only embedding model will perform badly on Hindi and Hinglish check-ins, and vernacular support is a stated core requirement, not a nice-to-have.

**Action before implementation**: confirm the exact current Voyage model name and embedding dimension directly against Voyage's own docs — I don't have live access to their catalog in this session, and model names/dimensions change. The architecture below is written generically (`VECTOR(N)`, dimension as a parameter) so this doesn't require a schema rewrite once confirmed, just filling in `N`.

**Selection criteria, in order:**

1. Multilingual, specifically strong on Hindi/Hinglish — not optional
2. Retrieval-optimized (some embedding models are tuned for classification/clustering, not similarity search — confirm the model is meant for retrieval)
3. Reasonable dimension size — smaller dimensions mean a cheaper, faster pgvector index; only pay for a larger one if retrieval quality on vernacular text actually needs it

### Generation model tiers — a recommendation, not a default

The project's own `bandhu-research-resources.md` already set the principle: *"Use a fast/cheap model for the phrasing step... reserve the tone evaluator for a sampled percentage."* That's a real architectural reason to use different model tiers for different pipeline stages — not cost-cutting for its own sake. Concretely, mapped onto `pipeline.html`'s stages:


| Stage                        | What it needs                                                                  | Suggested tier                   | Why                                                                                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------ | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Stage 7 — Orchestrator       | Judgment: eligible or not, which tool, does this feel right                    | Higher-quality tier (Opus-class) | This is the one place in the whole pipeline with real discretion — worth paying for good judgment here specifically                 |
| Stage 8 — Generate           | Phrasing only, constrained to retrieved content, ~60-word cap                  | Fast/cheap tier (Haiku-class)    | Small, bounded task — compose, don't decide. This is the "reserve the smart model for judgment, not phrasing" principle in practice |
| Stage 11 — Summarizer        | Synthesize structured facts into a short narrative                             | Mid tier (Sonnet-class)          | More than pure phrasing, less than live judgment — periodic and async, so latency matters less than on stages 7/8                   |
| Stage 12 — Sampled evaluator | Score against the MITI rubric — needs real judgment to be a trustworthy signal | Higher-quality tier (Opus-class) | Only runs on 5-10% of responses, so cost is already controlled by the sampling rate, not by using a cheaper judge                   |


This is a starting recommendation, not a locked decision — model choice is genuinely yours to make per stage, and the right call may shift once there's real usage data on cost and quality. The one part of this that isn't a preference: don't use the cheap/fast tier for the Orchestrator or the Evaluator — those are exactly the two places the pipeline is relying on judgment, and that's specifically what the fast tier trades away.

---

## 2. Schema

One Supabase Postgres database, one `pgvector` extension, every table below in it. Tables are grouped by what they're for, not by database boundary — there isn't one anymore.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

-- ============================================================
-- Content library — general retrievable entries (vetted/*.md)
-- ============================================================
CREATE TABLE content_entries (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entry_key       TEXT UNIQUE NOT NULL,      -- matches VETTING.md ids: 'gp-001', 'tt-003', 'ld-001'...
  text            TEXT NOT NULL,             -- the chunk itself, 1-3 sentences per the chunking rule
  category        TEXT NOT NULL,             -- grounding-technique | thinking-trap | life-decision-reflection | dependency-reflection
  tags            TEXT[] NOT NULL DEFAULT '{}',
  language        TEXT NOT NULL DEFAULT 'en',
  risk_tier       TEXT NOT NULL CHECK (risk_tier IN ('low','medium','high')),
  status          TEXT NOT NULL CHECK (status IN ('ai-drafted','self-vetted','pending-professional-review','professional-reviewed')),
  source_citation TEXT,                      -- e.g. "WHO mhGAP Intervention Guide 2.0, DEP 2.3, p.27"
  embedding       VECTOR(1024),              -- dimension placeholder — confirm against the chosen embedding model
  search_vector   tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,  -- for the
                                              -- hybrid-search option in §3; generated column, no extra writes needed
  vetted_by       TEXT,
  vetted_date     DATE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Metadata pre-filter BEFORE the vector search touches the index
CREATE INDEX content_entries_category_idx ON content_entries (category);
CREATE INDEX content_entries_tags_idx      ON content_entries USING gin (tags);
CREATE INDEX content_entries_lang_idx      ON content_entries (language);
CREATE INDEX content_entries_search_idx    ON content_entries USING gin (search_vector);

-- HNSW: better query latency than IVFFlat at this corpus size (low hundreds to low
-- thousands of entries — a curated corpus per the chunking rule, never a document dump)
CREATE INDEX content_entries_embedding_idx ON content_entries
  USING hnsw (embedding vector_cosine_ops);

-- Never embed anything above 'medium' risk tier into this table — enforce it here,
-- not just in application code. This is a real structural guarantee again now that
-- content lives in Postgres — it was only an application-level promise during the
-- Weaviate detour, since Weaviate has no equivalent CHECK constraint mechanism.
ALTER TABLE content_entries ADD CONSTRAINT no_high_risk_embedding
  CHECK (risk_tier != 'high');


-- ============================================================
-- Fixed redirect templates — NOT embedded, direct lookup only
-- ============================================================
CREATE TABLE redirect_templates (
  category      TEXT PRIMARY KEY CHECK (category IN
                  ('redirect-medical','redirect-disorder','redirect-medication','redirect-document')),
  template_text TEXT NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('ai-drafted','self-vetted','pending-professional-review','professional-reviewed')),
  vetted_by     TEXT,
  vetted_date   DATE,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- Safety gate — crisis-language patterns (safety/crisis-language-patterns.md)
-- Not vectorized: pattern matching needs to be exact/auditable, not similarity-based.
-- ============================================================
CREATE TABLE safety_patterns (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pattern       TEXT NOT NULL,
  pattern_type  TEXT NOT NULL CHECK (pattern_type IN ('direct','indirect','self-harm')),
  language      TEXT NOT NULL DEFAULT 'en',
  status        TEXT NOT NULL CHECK (status IN ('ai-drafted','self-vetted','pending-professional-review','professional-reviewed')),
  active        BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX safety_patterns_active_idx ON safety_patterns (active) WHERE active;


-- ============================================================
-- Helpline directory — phone numbers require live verification, not just review.
-- ============================================================
CREATE TABLE helplines (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_name      TEXT NOT NULL,
  phone_number  TEXT NOT NULL,
  hours         TEXT,
  audience      TEXT NOT NULL DEFAULT 'general' CHECK (audience IN ('general','minor')),
  verified_at   TIMESTAMPTZ,   -- NULL = not confirmed live. Application code must refuse
                                -- to serve a helpline row where this is NULL or stale.
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- Anonymous sessions — one row per browser, the anchor for the 2-week cleanup job.
-- No auth on this app; session_id is a UUID issued via cookie on first visit
-- (see docs/backend-architecture.md for the issuance/cleanup mechanics).
-- ============================================================
CREATE TABLE user_sessions (
  session_id                UUID PRIMARY KEY,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_active_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Resolves the "safety gate needs a per-conversation already-shown flag" open
  -- item from pipeline.html — a triggered crisis card doesn't re-fire on every
  -- message once it's already been shown recently. See backend-architecture.md §5.
  last_crisis_card_shown_at TIMESTAMPTZ
);
CREATE INDEX user_sessions_last_active_idx ON user_sessions (last_active_at);
-- The cleanup job's entire query: DELETE FROM user_sessions WHERE last_active_at < now() - interval '14 days'
-- ON DELETE CASCADE below means deleting the session row deletes everything that
-- references it in one statement — no multi-table cleanup script to keep in sync.

-- ============================================================
-- Conversation buffer — short-term, same-sitting memory (NOT the long-term
-- summary below). Core component for a chatbot flow specifically: without it,
-- turn N has no idea what was said in turns 1..N-1 of the same conversation.
-- See backend-architecture.md §2 for the full read/write logic.
-- ============================================================
CREATE TABLE conversation_turns (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  UUID NOT NULL REFERENCES user_sessions(session_id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content     TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX conversation_turns_session_idx ON conversation_turns (session_id, created_at DESC);
-- No separate trim/cleanup job needed: ON DELETE CASCADE from user_sessions bounds
-- total retention to 14 days already. What's bounded separately, at READ time (not
-- storage time), is how much of this a single Generate/Orchestrator call actually
-- sees — see backend-architecture.md §2's query, which filters by both recency and
-- row count so the prompt doesn't grow unbounded even in one very long sitting.

-- ============================================================
-- Per-user structured memory — small, per-check-in facts
-- (pipeline.html stages 4/5/10 read/write this; never vector-searched)
-- ============================================================
CREATE TABLE user_checkins (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id            UUID NOT NULL REFERENCES user_sessions(session_id) ON DELETE CASCADE,
  mood_tag              TEXT,
  theme                 TEXT,
  -- A real, enforceable foreign key again — content_entries and user_checkins are
  -- back in the same database, so this constraint actually does something now.
  -- It was a plain TEXT column with no REFERENCES during both the two-database
  -- and Weaviate phases, since neither allowed a cross-system/cross-database FK.
  suggestion_entry_key  TEXT REFERENCES content_entries(entry_key),
  suggestion_helped      BOOLEAN,          -- null = never asked / not answered
  is_help_offer         BOOLEAN NOT NULL DEFAULT false,  -- feeds the stage-5 eligibility-gate count;
                                                          -- close_the_loop turns stay false, per the
                                                          -- "care isn't rationed" design principle
  input_mode            TEXT CHECK (input_mode IN ('text','voice')),  -- how the message arrived —
                                                          -- see backend-architecture.md §5. Never
                                                          -- stores audio itself, just which channel
                                                          -- it came in on, for future analytics.
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX user_checkins_recent_idx ON user_checkins (session_id, created_at DESC);

-- The eligibility gate's rolling count (stage 5) is a query, not a stored counter —
-- avoids a second write path that could drift from the source-of-truth checkins:
--   SELECT count(*) FILTER (WHERE is_help_offer)
--   FROM user_checkins
--   WHERE session_id = $1 AND created_at > now() - interval '3 checkins'  -- see open item below


-- ============================================================
-- User creations — images and poems the person made (NOT music — Listen,
-- below, turned out to be Bandhu-provided curated audio, not something the
-- person creates; see backend-architecture.md §13 for how that got clarified).
-- Captioned for the Summarizer's bigger-picture narrative (stage 11 reads
-- `caption`, never `text_content` or the stored file itself — same
-- "impression, not replay" principle as everywhere else memory shows up in
-- this design). Same 14-day retention as everything else — cascades away
-- with the session, no special lifecycle of its own.
-- "Write Together" and "Poem" are two Home-screen entry points into this
-- same table/flow, not two separate features — no schema implication.
-- ============================================================
CREATE TABLE user_creations (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id     UUID NOT NULL REFERENCES user_sessions(session_id) ON DELETE CASCADE,
  creation_type  TEXT NOT NULL CHECK (creation_type IN ('image','poem')),
  text_content   TEXT,          -- populated for 'poem' only — the poem itself, plain text
  storage_path   TEXT,          -- populated for 'image' only — path into the Supabase
                                 -- Storage bucket, not the file itself
  caption        TEXT NOT NULL, -- short description of what this is — this is what stage 11
                                 -- actually reads, never the full poem or the file
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX user_creations_session_idx ON user_creations (session_id, created_at DESC);
-- Exactly one of text_content / storage_path should be populated, matching creation_type.
-- A CHECK constraint spanning nullable columns tied to a third column's value is awkward
-- in Postgres — this is enforced at the application layer, not the database, worth knowing.


-- ============================================================
-- Listen — curated audio tracks Bandhu offers, NOT user-generated. Shared,
-- non-personal content (belongs conceptually with content_entries and
-- redirect_templates, not with per-user data), so no session_id here. Not
-- vector-embedded — a small curated set, filtered by mood_tags directly
-- rather than similarity search, same pattern as redirect_templates' direct
-- category lookup.
-- ============================================================
CREATE TABLE audio_tracks (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title         TEXT NOT NULL,
  storage_path  TEXT NOT NULL,     -- path into Supabase Storage — the actual audio file
  mood_tags     TEXT[] NOT NULL DEFAULT '{}',  -- e.g. 'anxious', 'low-energy' — matched against
                                                -- the same tags Classify already produces
  duration_seconds INTEGER,
  status        TEXT NOT NULL CHECK (status IN ('ai-drafted','self-vetted','pending-professional-review','professional-reviewed')),
  active        BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audio_tracks_mood_idx ON audio_tracks USING gin (mood_tags);
-- The `status` gate reuses VETTING.md's enum even though there's no clinical content here —
-- licensing/rights-clearance for each track is its own review step, and this column is where
-- that gets tracked, so "vetted" means "cleared to use," not just "sounds nice."


-- ============================================================
-- Summarizer output — the rolling narrative (pipeline.html stage 11)
-- ============================================================
CREATE TABLE user_memory_summary (
  session_id    UUID PRIMARY KEY REFERENCES user_sessions(session_id) ON DELETE CASCADE,
  summary_text  TEXT NOT NULL,           -- a few sentences, never a transcript
  window_start  DATE,
  window_end    DATE,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- Sampled evaluator log (pipeline.html stage 12, async, 5-10% of responses)
-- ============================================================
CREATE TABLE evaluator_scores (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  checkin_id               UUID REFERENCES user_checkins(id) ON DELETE CASCADE,
  miti_scores               JSONB,     -- structured MITI dimensions, not free text
  acknowledgment_complete   BOOLEAN,    -- the "does this stand alone" axis from pipeline.html
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**On `session_id` replacing `user_id`**: this app has no authentication (see `docs/backend-architecture.md`), so there's no durable identity to key on. `session_id` is the anonymous cookie-issued UUID described there. If auth ever gets added later, it's an additive column (`account_id`, nullable, linked at login time), not a rename — nothing here needs to change to support that later.

---

## 3. Retrieval — metadata filter first, similarity second, hybrid optional

This is the concrete SQL behind `pipeline.html` stage 6, and it directly implements the RAG design guideline from `bandhu-research-resources.md`: *"Pre-filter by metadata before running vector similarity search."*

### Baseline query — pure vector similarity

```sql
SELECT entry_key, text, category, tags
FROM content_entries
WHERE category = ANY($1)              -- from Classify (stage 3) — narrows the search space first
  AND language = $2                    -- detected language, incl. code-mixed handling
  AND risk_tier IN ('low', 'medium')   -- structural guarantee: high-risk never reachable by similarity search
ORDER BY embedding <=> $3              -- cosine distance against the query embedding, only across the pre-filtered rows
LIMIT 3;
```

Why the `WHERE` clause comes before the `ORDER BY ... <=>`: pgvector's HNSW index is fast, but it's still cheaper and more precise to shrink the candidate set with an ordinary B-tree/GIN filter first — this is the same principle the resources doc states directly (fewer, more relevant chunks, not a bigger `top_k`).

**Thinking Trap re-entry** (the branch documented in `pipeline.html` row 7) runs the same query shape with one difference — `category = 'thinking-trap'` and an additional filter on the specific pattern the person selected (`tags @> ARRAY[$selected_pattern]`), not the general emotion tag from Classify.

### Optional upgrade — hybrid (vector + keyword), via Reciprocal Rank Fusion

Not built by default — add this only if pure vector similarity is observed missing an exact-phrase match a keyword search would've caught. The `search_vector` generated column in §2 makes this possible without re-embedding anything:

```sql
WITH vector_results AS (
  SELECT entry_key, row_number() OVER (ORDER BY embedding <=> $3) AS rank
  FROM content_entries
  WHERE category = ANY($1) AND language = $2 AND risk_tier IN ('low','medium')
  LIMIT 20
),
keyword_results AS (
  SELECT entry_key, row_number() OVER (ORDER BY ts_rank(search_vector, websearch_to_tsquery('english', $4)) DESC) AS rank
  FROM content_entries
  WHERE category = ANY($1) AND language = $2 AND risk_tier IN ('low','medium')
  LIMIT 20
)
SELECT entry_key, (1.0 / (60 + COALESCE(v.rank, 1000))) + (1.0 / (60 + COALESCE(k.rank, 1000))) AS score
FROM vector_results v
FULL OUTER JOIN keyword_results k USING (entry_key)
ORDER BY score DESC
LIMIT 3;
```

This is the manual side of the pgvector-vs-Weaviate tradeoff discussed in `backend-architecture.md` — Weaviate's `.query.hybrid()` does this fusion in one call; here it's a SQL function you own. The constant `60` is RRF's standard smoothing parameter (from the original paper), not something specific to this project — leave it as-is unless you have a specific reason to tune it.

---

## 4. Ingestion pipeline — how `vetted/*.md` becomes retrievable

No automatic chunking algorithm needed. Per `VETTING.md`, every entry is already hand-authored as one chunk (`## Entry: gp-001` blocks with YAML frontmatter). The ingestion job is a parser, not a text-splitter:

1. Walk `knowledge-base/vetted/*.md`
2. For each `## Entry:` block, parse the fenced YAML frontmatter into columns (`category`, `tags`, `risk_tier`, `status`, source citation) and the following paragraph as `text`
3. **Gate on `status`** — only `self-vetted` or `professional-reviewed` entries get embedded and inserted. `ai-drafted` entries are parsed and validated (catches schema errors early) but never make it into `content_entries` until a human actually changed the status — this is the enforcement point for the whole `VETTING.md` process, not just a convention
4. Call the embedding provider once per entry, store the vector
5. Upsert on `entry_key`:
   ```sql
   INSERT INTO content_entries (entry_key, text, category, tags, language, risk_tier, status, source_citation, embedding, vetted_by, vetted_date)
   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
   ON CONFLICT (entry_key) DO UPDATE SET
     text = EXCLUDED.text, tags = EXCLUDED.tags, status = EXCLUDED.status,
     embedding = EXCLUDED.embedding, vetted_by = EXCLUDED.vetted_by,
     vetted_date = EXCLUDED.vetted_date, updated_at = now();
   ```
   Re-running ingestion after an edit updates the row rather than duplicating it.

`redirect_templates` and `safety_patterns` follow the same gate, but stricter: only `professional-reviewed` status is eligible for ingestion, matching their `high` risk tier — a `self-vetted`-only redirect template or crisis pattern should never reach the live table, per `VETTING.md`'s tiering. **As of 2026-07-11, none of the four redirect templates or the crisis-pattern list are `professional-reviewed`** — they're `self-vetted` at the founder's explicit call for demo purposes (see the deviation note in `VETTING.md`), which means this gate currently blocks all of them from ingestion. That's the gate working as designed, not a bug to route around before the real review happens.

---

## 5. Open items

- **Embedding provider and dimension are placeholders.** `VECTOR(1024)` needs to become the real number once the exact Voyage (or alternative) model is confirmed against their current docs — this isn't a guess I should lock in.
- **Hybrid search (§3) is written but not wired in** — add it only once pure vector search is observed missing something, per the reasoning above. Don't build it preemptively.
- **Eligibility gate's "last 3 check-ins" window** — the query sketch in §2 uses a time-based comment placeholder; needs a real definition (last N check-ins by count, or a rolling calendar window) tied to the same open decision already flagged in `pipeline.html`'s open items (the proposed "1 in 3" cap isn't validated yet).
- **`helplines.verified_at`** — the column exists, but the actual verification (calling each number, confirming hours) is the task from `knowledge-base/safety/helpline-directory.md` that still hasn't happened. The schema won't stop someone from inserting an unverified row; that's an application-level and process-level guarantee, not a database one.
- **Summarizer trigger** (stage 11) — same open item as `pipeline.html`: nightly batch vs. rolling recompute vs. on-demand isn't decided, which affects whether `user_memory_summary` gets updated by a cron job, a queue consumer, or inline during Memory write. See `docs/backend-architecture.md` for how this maps onto an actual process.
- **`conversation_turns`' read-time window (2 hours / last 12 rows) is a starting guess**, not validated — see `backend-architecture.md` §2. Storage retention is already bounded (14-day cascade); this is purely about how much recent dialogue a single Claude call gets shown.
- **High-risk knowledge-base files are `self-vetted`, not `professional-reviewed`, as of 2026-07-11** — the ingestion gate (§4) correctly blocks them from `redirect_templates`/`safety_patterns` until that changes; noting it here too so this doc doesn't read as if they're live.
- **Resolved by this pass, noted so it isn't re-litigated**: `suggestion_entry_key` is a real foreign key again (§2) — the cross-database/cross-system referential-integrity gap from the two prior versions of this doc no longer exists, since everything lives in one Supabase database now. Similarly, `no_high_risk_embedding` is a real `CHECK` constraint again, not an application-level-only promise.
- **`user_creations.caption` — who writes it, isn't decided.** Options: the person types their own short description when they create something, or a Claude call looks at the poem/image and writes one automatically. Affects whether this needs a Claude call in the creation flow at all, and whether a caption could ever say something the person didn't intend — worth a real decision, not a default.
- **`user_creations`'s exactly-one-of-`text_content`/`storage_path` rule is application-level only** (§2) — same category of gap as the embedding risk-tier constraint used to be, just not one Postgres can enforce here regardless of which database technology is used, since it depends on a third column's value.
- **`audio_tracks` needs an actual curated source, and real rights clearance.** The table assumes someone (you) picks and licenses a small set of tracks — nothing here sources them. This is a content/legal question, not a schema one, and worth resolving before `active` is ever set `true` on a real row, same spirit as `VETTING.md`'s stance on the redirect templates.
- **Co-Create and Listen are both still an open README-level product decision** — ship in v1, or wait for the core loop to validate first (`docs/ux-flow.html`'s own note). Schema exists for both now per your explicit call to build them, but that doesn't resolve the underlying product question — worth revisiting explicitly before either ships to real users.
