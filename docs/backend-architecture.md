# Backend architecture

Companion to `docs/pipeline.html` (the 12-stage flow) and `docs/vector-database.md` (Supabase/Postgres + pgvector schema). This doc is the layer those two don't cover: how memory actually works for a multi-turn chat, how voice fits in, what process runs the pipeline, how an anonymous browser becomes an identity, what stops abuse, and how you'd actually see what happened after the fact.

Written for a first backend project specifically — each section says *what* to build and *why*, not just the shape of it, since the point here is to learn the pattern, not just get working code.

**Terms used throughout**: a **message** is one thing the person sends — text or voice. A **turn** is one message + Bandhu's one reply — the atomic unit every pipeline stage processes, and what `user_checkins` and `conversation_turns` each store one row per. A **sitting** isn't a stored concept — it's just turns close together in time, and §2 explains how that's detected without needing to track session boundaries explicitly.

---

## 1. Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python | Your call, confirmed. Also the natural fit — every other piece here (Anthropic SDK, Voyage SDK, `psycopg`/`supabase-py`, OpenTelemetry) has a first-class Python client. |
| Web framework | FastAPI | Async-native, which matters because almost everything this backend does is waiting on a network call (Claude, Voyage, Postgres, and now STT/TTS) rather than computing — async lets one process handle many concurrent turns instead of one thread blocking per request. Also gives you request/response validation via Pydantic for free, which catches shape bugs before they reach a pipeline stage. |
| Database | Supabase (PostgreSQL + `pgvector`) | One database, content and user data both — per `vector-database.md` §1. Free tier, no separate vector-database service to run. Also holds the conversation buffer (§2) — no separate memory store needed. |
| Object storage | Supabase Storage | S3-compatible, same free Supabase project — holds image creations (§12) and curated Listen audio (§13). Poems are plain text and skip this entirely. |
| ORM / migrations | SQLAlchemy + Alembic | SQLAlchemy is the standard Python ORM (keeps table definitions as Python classes instead of hand-written SQL scattered through the app); Alembic tracks schema changes as versioned migration files, so "add a column" becomes a reviewable diff instead of a manual `ALTER TABLE` you have to remember to run against every environment. |
| Embeddings | Voyage AI | Per `vector-database.md` §1 — Anthropic has no embeddings API. |
| Generation | Claude (Anthropic SDK, official `anthropic` Python package) | Per the model-tier table in `vector-database.md` §1. |
| Speech-to-text | Not locked — see §5 | Needs strong Hindi/Hinglish (code-mixed) accuracy, same hard requirement as embeddings. Candidates to verify, not assume: OpenAI Whisper (broad multilingual, well documented), Sarvam AI / Bhashini (India-first, may handle code-switched speech better — Bhashini specifically is India's own public multilingual speech stack). |
| Text-to-speech | Not locked — see §5 | Same language requirement, plus voice quality/warmth matters for a companion product specifically. Candidates: ElevenLabs (strong multilingual quality), Sarvam AI (India-first voices). |
| Rate limiting | `slowapi` | A FastAPI-native wrapper around the `limits` library — in-memory backend by default, which is enough for a single-instance solo deployment (see §8's note on when this stops being true). |
| Scheduled jobs | APScheduler (in-process) | Runs the cleanup job (§9) and can run the Summarizer (stage 11 below) without standing up a separate task queue. Simplest thing that works at this scale — see §9 for the upgrade path if job volume ever grows. |
| Telemetry | Langfuse Cloud (free Hobby tier) + OpenTelemetry | Originally Phoenix per the original ask; switched after comparing free-tier options — see §10 for the reasoning and the open item on session-id retention. |

---

## 2. Memory — two horizons

This is a core component for a chatbot flow specifically, not incidental plumbing — get it wrong and every reply either forgets what was just said two messages ago, or ends up reciting a file on the person like a case log. Two structurally separate things share the word "memory" here, and treating them as one was the actual gap in an earlier version of this doc:

| | Conversation buffer | Rolling summary |
|---|---|---|
| Table | `conversation_turns` | `user_memory_summary` |
| Horizon | Same sitting — last ~12 turns, only if within the last 2 hours | Cross-day / cross-week — a synthesized narrative |
| Content | Raw text, verbatim (transcribed, if the turn arrived as voice — see §5) | Synthesized facts, never a direct quote |
| Written | Every turn (stage 10) | Periodically, async (stage 11) |
| Read by | Safety gate (2), Orchestrator (7), Generate (8) | Orchestrator (7), via Memory read (4) |
| Feeds Claude as | The `messages` array | A block inside the `system` prompt |
| Purpose | Coherence within this conversation | Long-term pattern awareness across visits |
| Never does | Get summarized; get shown to the person as a recap | Contain a verbatim quote presented as if just said |

**Why two, not one**: with only the long-term summary, a conversation would feel amnesiac mid-chat — the summary only updates periodically, not every turn, so Claude would forget what was said two messages ago. With only a raw buffer and no periodic synthesis, it either grows into a literal transcript (exactly what the README's "never a data recap" rule excludes) or gets truncated and any pattern from before the cutoff is just gone. Each solves a problem the other structurally can't.

**Read query** (Memory read, stage 4):
```sql
SELECT role, content, created_at FROM (
  SELECT role, content, created_at FROM conversation_turns
  WHERE session_id = $1
    AND created_at > now() - interval '2 hours'
  ORDER BY created_at DESC
  LIMIT 12
) recent
ORDER BY created_at ASC;
```
The 2-hour filter is what makes this "same sitting" without tracking session boundaries explicitly — it's just "is the last thing said recent enough to still be a live conversation." Come back tomorrow and this returns nothing; the long-term summary — already synthesized, already softened — is what carries continuity across that gap, not a raw quote from yesterday surfacing unprompted today.

**Why the subquery, not a single `ORDER BY ... ASC LIMIT 12`**: a single ascending-order query with `LIMIT 12` returns the *oldest* 12 turns inside the 2-hour window, not the most recent 12 — wrong once a conversation has more than 12 turns in that window, since it would show Claude stale early turns and silently drop the most recent ones. The inner query grabs the most recent 12 (descending, limited), the outer query just re-sorts that small set back into chronological order for the `messages` array.

**Write** (Memory write, stage 10): after Generate produces a reply, insert two rows — the person's message (transcribed text, if voice) and Bandhu's reply, both under the current `session_id`. No trimming needed at write time: the 14-day cascade from `user_sessions` already bounds total storage (`vector-database.md` §2), and the read query above is what bounds how much of it Claude actually sees on any given turn.

**This resolves an existing open item.** `pipeline.html` flags "Safety gate needs conversation memory" as a build-blocker — the hedge case ("just thinking about it," following a direct statement earlier in the conversation) can't be caught from one message alone. The Safety gate (stage 2) now reads the same `conversation_turns` window Memory read does, so a hedge in message 4 can be checked against a direct statement in message 2. The "already shown" flag that same open item calls for is `user_sessions.last_crisis_card_shown_at` (`vector-database.md` §2) — if a crisis card fired recently in this session, it doesn't re-render on every subsequent message, though the underlying match still runs every time; suppression is a display decision, never a detection skip.

---

## 3. Request lifecycle

```
Browser                    FastAPI                          External systems
   │                          │
   │  POST /message           │
   │  text OR audio blob      │
   │  (cookie: bandhu_sid?)   │
   ├─────────────────────────►│
   │                          │  Session middleware — issue/validate bandhu_sid → user_sessions
   │                          │  Rate-limit middleware — session_id under quota? No → 429, stop
   │                          │
   │                          │  If audio: STT first (§5) — everything past this point is text
   │                          │
   │                          │  Pipeline orchestrator runs (12 stages, detailed in §4) ────────┐
   │                          │  Memory read pulls BOTH horizons from §2 before Orchestrator/    │
   │                          │  Generate ever run.                                              │
   │                          │                                                                  │
   │                          │  If the turn came in as voice: TTS after Guardrail passes (§5)   │
   │  200, response body      │◄─────────────────────────────────────────────────────────────────┘
   │  (text, +audio if voice) │
   │  Set-Cookie if new sid   │
   │◄─────────────────────────┤
   │                          │  Async, doesn't block the response:
   │                          │  Summarizer (periodic) ──► user_memory_summary
   │                          │  Sampled evaluator ──────► evaluator_scores
   │                          │
   │                          │  Every stage emits an OpenTelemetry span → Langfuse (§10)
```

**Steps before the pipeline are synchronous** — the person is waiting. The async tail runs after the response is already sent (FastAPI's `BackgroundTasks`, or picked up by APScheduler on its own schedule) — nothing about summarization or evaluation should add latency to the thing someone's actually staring at. The pipeline orchestrator itself is not one function — it's the 12 stages below as separate, individually testable steps, with the branches (crisis response, special-case redirect, thinking-trap re-entry) as early returns out of that sequence.

---

## 4. Component logic — one by one

Every stage: the plain-language version of what it's for, then what it receives, what it actually does, and what it hands to the next stage.

**1 — Ingest & normalize**
- *In plain terms*: the message comes in — typed, spoken, or a photo. Spoken gets turned into text immediately, and the recording itself is thrown away. A photo gets a quick check for whether it's a medical document before anything else touches it. Typed text just gets a language check.
- *Input*: raw message — text, image, **or now audio** — plus `session_id` (already resolved by session middleware)
- *Logic*: if audio, run it through STT first (§5) — the transcribed text plus detected language is what this stage actually normalizes; everything from here on treats a voice turn identically to a typed one. If the message is an image, classify photo-vs-medical-document **before anything else touches it** — this has to be the first thing that happens to an image, not a later check, per `pipeline.html`'s own open item on this. Text needs language detection, including code-mixed Hindi/English.
- *Output*: normalized `Message{text, language, media_type, input_mode}` — `input_mode` is `'text'` or `'voice'`, carried through to `user_checkins` (`vector-database.md` §2) for later analytics; it never implies anything downstream behaves differently except at the response end (§5).

**2 — Safety gate**
- *In plain terms*: before anything else, check the message and the last few things said for any sign the person might be in real danger. If something's there, everything below stops and the crisis response takes over instead — this is the very first thing that runs, not a maybe-later step.
- *Input*: normalized message + conversation buffer (§2, 2-hour window) + `user_sessions.last_crisis_card_shown_at`
- *Logic*: pattern-match current message and buffer against `safety_patterns`; a hedge only counts as a hedge if a direct statement appears in the buffer. Suppress re-rendering the crisis card if one fired recently in this session, but always re-run the match (suppression is a UI decision, not a detection skip).
- *Output*: `{triggered: bool, severity}`. Triggered → short-circuit straight to the Crisis branch, skip everything below.

**3 — Classify**
- *In plain terms*: a quick read on the emotional tone of just this message — sad, anxious, stressed. Also catches a few danger zones ("do I have depression," "what medication should I take") and routes those to a pre-written, careful redirect instead of letting anything improvise an answer.
- *Input*: normalized message only (not the buffer — classification is about what *this* message contains, not the conversation's drift)
- *Logic*: Claude fast-tier call; produces emotion/category/intensity tags, or flags one of the 4 special-case categories (`redirect-medical`/`redirect-disorder`/`redirect-medication`/`redirect-document`, `vector-database.md` §2)
- *Output*: `tags{}` or `special_case`. Special case → short-circuit to the fixed redirect-template branch, bypassing Retrieval/Orchestrator/Generate entirely.
- *Low-confidence path* (resolves `pipeline.html`'s "Classify needs an explicit low-confidence path" open item): a genuinely ambiguous message ("idk", a bare emoji) — or a malformed/out-of-schema model response — both resolve to `confidence: "low"` with every tag left `null`, never force-fit onto the nearest category. The Orchestrator treats this the same way either way: default to a plain open acknowledgment, nothing forced. See `app/pipeline/stages/classify.py`.

**4 — Memory read**
- *In plain terms*: pull up who we're talking to — the last few things said in this sitting (so the reply doesn't sound like it forgot), and a softened, longer-term impression of how this person's been doing lately.
- *Input*: `session_id`
- *Logic*: two reads, both described in §2 — `user_memory_summary` (long-term) and `conversation_turns` (short-term, time+count bounded)
- *Output*: `{summary_text, recent_turns[]}`

**5 — Eligibility gate**
- *In plain terms*: check whether a suggestion has already been offered too many times recently, so Bandhu doesn't feel like it's constantly pitching things. Just following up on something already offered doesn't count as a new offer.
- *Input*: `session_id`
- *Logic*: count `is_help_offer = true` over the last 3 rows in `user_checkins` (not `conversation_turns` — this counts structured suggestion-offer events, not raw messages); `close_the_loop` turns never count against this, per the "care isn't rationed" principle
- *Output*: `eligible_for_offer: bool`

**6 — Retrieval**
- *In plain terms*: based on the emotional tag from step 3, pull a couple of short, pre-approved pieces of content — a grounding technique, a way of reframing a thought — from a small, human-reviewed library. Nothing invented, only retrieved.
- *Input*: Classify's `tags` + detected language (not the conversation buffer, deliberately — keeps search anchored to what was just said instead of drifting toward whatever the last few messages happened to be about)
- *Logic*: `pgvector` query — metadata `WHERE` filter, then `ORDER BY embedding <=> ...`, top 2-3 chunks (`vector-database.md` §3)
- *Output*: `retrieved_chunks[]`
- *Deferred*: an earlier doc (`rag-components.html`) proposed a Redis/Upstash cache in front of this stage. Not built — no traffic volume yet to justify it, and it's another external service. See §14 for the corrected design if it's ever worth revisiting.

**7 — Orchestrator (judgment)**
- *In plain terms*: the one real decision in the whole flow. Everything gathered so far goes here, and it decides: acknowledge and stop, gently offer something, point out a thinking pattern, or just stay quiet. Quiet is the default — something has to earn its way into the reply.
- *Input*: current message, `tags`, `{summary_text, recent_turns[]}` from stage 4, `eligible_for_offer`, `retrieved_chunks[]`
- *Logic*: the one Claude Opus-tier call with real discretion — decides `close_the_loop?` / `offer_suggestion?` / `notice_thinking_trap?` / silence (the default). This is the stage that actually needs `recent_turns` — recognizing "I already offered this two messages ago, don't repeat it" requires seeing the buffer, not just the summary.
- *Output*: `directive{tool, target_content_or_none}`

**8 — Generate**
- *In plain terms*: write the actual reply. Doesn't decide anything new — just phrases whatever stage 7 decided into a short, warm sentence or two, using only what it was handed.
- *Input*: `directive` from stage 7 + whatever content it points to + `recent_turns` (for phrasing continuity) + current message
- *Logic*: Claude fast-tier call, phrasing only, ~60-word cap, constrained to only use what's handed to it. §6 shows exactly how this assembles into an API call. Output is always text at this point — voice synthesis, if needed, happens after Guardrail, not here (§5): Generate shouldn't have to think about output modality, only phrasing.
- *Output*: `response_text`

**9 — Guardrail check**
- *In plain terms*: double-check the drafted reply before it goes out — did it accidentally sound like a diagnosis, a recommendation, anything it shouldn't. If it slips, swap it for a safe fallback instead of sending it as-is.
- *Input*: `response_text` + the hard-constraint list (never diagnose, never recommend, etc.)
- *Logic*: rule engine / secondary check for violations.
- *Output*: pass → send; fail → fallback safe response instead.

**10 — Memory write → response**
- *In plain terms*: save what happened this turn, then send the reply. If the person spoke to Bandhu, this is also where the reply gets turned into audio before it goes back.
- *Input*: everything produced this turn
- *Logic*: insert a `user_checkins` row (structured facts + `input_mode`); insert 2 `conversation_turns` rows (person's message, Bandhu's reply — text only, even for a voice turn). If `input_mode == 'voice'`, run TTS on `response_text` now (§5) before responding.
- *Output*: response sent to the browser — text always, audio alongside it if the turn was voice.

**11 — Summarizer** *(async)*
- *In plain terms*: every so often, not every turn, take stock — look back at recent facts (and anything created, per §12) and rewrite the longer-term summary in a few sentences, so a later conversation still feels like it remembers an earlier one, without ever storing or repeating exact quotes.
- *Input*: accumulated `user_checkins` facts since the last run, plus any `user_creations.caption` rows in the same window (§12)
- *Logic*: Claude mid-tier call, synthesizes into a few-sentence narrative. Deliberately does **not** read `conversation_turns`, the full text of a poem, or a stored image/audio file — it summarizes structured facts and short captions, never raw dialogue or the creative work itself, so "never a transcript" holds at the synthesis layer too, not just at storage.
- *Output*: updates `user_memory_summary`

**12 — Sampled evaluator** *(async)*
- *In plain terms*: spot-check quality — on a small slice of replies, separate from the live conversation, grade the reply against a coaching-conversation rubric, purely so tone can be checked over time. Never affects what the person actually sees.
- *Input*: a sampled turn's `response_text` + the context that produced it
- *Logic*: Claude Opus-tier call, scores against the MITI rubric.
- *Output*: an `evaluator_scores` row

---

## 5. Voice input & output

Two edge adapters, not two new pipeline stages — everything between STT and TTS is the same 12-stage flow regardless of how the message arrived. That separation is deliberate: `pipeline.html`'s conversation logic shouldn't need to know or care whether someone typed or spoke.

### Voice in — before stage 1

```
Browser records audio (MediaRecorder) ──► POST /message, audio blob
        │
        ▼
  Duration/size check ─── over cap? ──► reject before paying for STT at all
        │
        ▼
  STT call (provider TBD, §1) ──► {text, detected_language}
        │
        ▼
  Discard the audio blob — never written to disk or object storage
        │
        ▼
  Continues as a normal Message{text, language, input_mode:'voice'} into stage 1
```

**The privacy point, stated plainly**: a voice recording is a strictly more sensitive artifact than its text transcript — it carries tone, identity, and emotional state in a way text doesn't, especially for someone using this app in distress. The "never a data recap / never a permanent transcript" principle that already governs `conversation_turns` (§2) applies at least as strongly here, arguably more. The design commitment: **audio is transcribed and immediately discarded, never persisted** — not to a bucket, not to a temp table, not even transiently beyond what the STT call itself needs. Only the transcribed text ever reaches `conversation_turns` or `user_checkins`.

**Duration/size cap before the STT call, not after**: STT is a paid, per-second API call — checking a clip's length client-side (or from the upload's byte size server-side) before sending it anywhere means a malicious or buggy oversized upload gets rejected for free, instead of after you've already paid to transcribe it. A starting cap (60–90 seconds per message) is a guess — see §14.

### Voice out — after stage 9, inside stage 10

```
Guardrail check passes ──► response_text finalized
        │
        ▼
  input_mode == 'voice'? ──No──► respond with text only
        │
       Yes
        ▼
  TTS call (provider TBD, §1) ──► audio stream/URL
        │
        ▼
  Respond with {text, audio} — text always included, even on a voice turn,
  for accessibility and because conversation_turns needs the text regardless
```

`response_text` is what gets stored (§2, §4 stage 10) and what gets spoken — TTS runs on it, doesn't replace it. That keeps the conversation buffer's content uniform (always text) regardless of input or output modality, so Orchestrator/Generate never need to branch on how a past turn was delivered.

**Latency, named as a real UX concern, not solved here**: a voice turn now pays STT time, then the same two Claude calls (Orchestrator, Generate) a text turn pays, then TTS time. That's a longer round-trip than typing, and voice interactions are generally more latency-sensitive than text ones — a pause that reads as "thinking" in a chat window can read as "broken" in a voice call. Two options worth knowing about, neither committed to here: accept the added latency for a first version (simplest, and this pipeline's LLM calls are already the dominant cost, not the smallest part), or stream TTS synthesis as `response_text` is generated instead of waiting for the full string — meaningfully more complex to build correctly. Flagged in §14, not decided.

---

## 6. The Generate call, concretely

This is where the two memory horizons actually meet the Claude API, and it's the part worth being precise about rather than hand-wavy — note this is unaffected by voice (§5): by the time Generate runs, the turn is already plain text either way.

```python
# recent_turns is stage 4's output, oldest first
messages = [{"role": t.role, "content": t.content} for t in recent_turns]
messages.append({"role": "user", "content": current_message.text})

system_prompt = f"""{BANDHU_PERSONA_AND_CONSTRAINTS}

Rolling context on this person — for your own awareness only, never to be
recited back to them:
{summary_text or "No prior context yet."}

{directive.as_prompt_block()}
# e.g. "Offer this, once, warmly, only if it fits naturally: <retrieved_chunk.text>"
"""

response = client.messages.create(
    model=GENERATE_MODEL,      # fast tier — vector-database.md §1
    max_tokens=150,
    system=system_prompt,
    messages=messages,
)
```

**Why the split matters, not just how it's coded**: the long-term summary and the Orchestrator's directive go into `system` — Claude knows them, but they're never something that could literally appear as a chat bubble, because they're not in the `messages` array. Only the actual back-and-forth (`recent_turns` plus the current message) goes into `messages`. This isn't just a style choice — it's what makes "never a data recap" structurally true instead of a prompt instruction Claude could ignore under the wrong circumstances: the summary physically cannot come out looking like "Last Tuesday you said X" in the way a `user`/`assistant` transcript entry would, because it was never written as if someone said it.

---

## 7. Anonymous identity — the `bandhu_sid` cookie

No login, no account — per the requirement, and consistent with the product's own "companion-first, not a data-collection tool" stance. But the pipeline still needs *something* stable to hang a person's turns and memory off of. That's `session_id`.

**Issuance** (session middleware, runs before every other middleware):
1. Read the `bandhu_sid` cookie off the incoming request.
2. If missing or not a valid UUID: generate one (`uuid.uuid4()`), `INSERT INTO user_sessions (session_id) VALUES (...)`, and set it on the response as a cookie.
3. If present and valid: `UPDATE user_sessions SET last_active_at = now() WHERE session_id = $1`. If that update matches zero rows (cookie exists but the session was already cleaned up, or was forged), treat it as missing and re-issue — don't trust a cookie whose row doesn't exist.

**Cookie flags** (this is the part that's easy to get subtly wrong):
```python
response.set_cookie(
    key="bandhu_sid",
    value=str(session_id),
    max_age=60 * 60 * 24 * 14,   # 14 days, in seconds — matches the cleanup job's window exactly
    httponly=True,                 # JS on the page can't read or tamper with it
    secure=True,                   # only sent over HTTPS
    samesite="lax",                # sent on normal navigation to your own site; blocks most cross-site
                                    # abuse without breaking anything, since this isn't a cross-site
                                    # embedded widget
)
```
`httponly=True` matters specifically because `session_id` is the key to someone's conversation and memory — if it were readable by JS, any XSS bug anywhere on the page becomes a way to read that history, not just deface a page.

**Why the client can't just generate its own UUID in JS and send it as a header instead**: it could, technically, but then the server has to trust a value the browser fully controls, with no way to detect a forged/replayed id — a cookie the server issues (and can invalidate by not matching it to a row) is the safer default for something scoping private data, even anonymous data.

---

## 8. Rate limiting

Unauthenticated means the only identity you have to rate-limit against is `session_id` (once issued) and IP address (always available, even pre-cookie). Use both:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

def rate_limit_key(request):
    return request.cookies.get("bandhu_sid") or get_remote_address(request)

limiter = Limiter(key_func=rate_limit_key)

@app.post("/message")
@limiter.limit("20/10minutes")   # per session — generous for a real conversation, tight for a script
async def message(...): ...
```

Two layers, not one, because they catch different abuse shapes:
- **Per-session limit** (e.g. 20 requests/10min) — stops one runaway client (buggy retry loop, or someone deliberately hammering the endpoint) from burning API spend, which matters more now than before — a voice turn costs STT + 2 Claude calls + TTS, not just the 2 Claude calls a text turn costs.
- **Per-IP limit, looser** (e.g. 200 requests/10min) — a backstop against someone bypassing the session limit by discarding cookies and re-requesting a fresh `bandhu_sid` every time.
- **Voice-specific: the duration cap from §5** is really a third layer, applied before either of the above even matters for that request — rejecting an oversized clip costs nothing; rejecting a request that already made it through STT costs a paid API call.

Both request-count numbers above are starting points, same spirit as the model-tier table in `vector-database.md` — tune once you have real traffic, don't treat them as validated.

**The in-memory limitation, stated plainly**: `slowapi`'s default backend counts requests in the process's own memory. That's correct and sufficient for one backend process. The moment you run more than one process (multiple workers, multiple instances behind a load balancer), each process has its own independent counter, so the *effective* limit becomes `configured_limit × number_of_processes`. The fix at that point is pointing `slowapi` at a shared Redis backend instead of in-memory — a config change, not a redesign, but worth knowing about now rather than being surprised by it later.

---

## 9. Cleanup job — the 2-week expiry

One scheduled job, run daily (APScheduler `CronTrigger`, e.g. 3am local):

```python
def cleanup_expired_sessions(db):
    db.execute(
        "DELETE FROM user_sessions WHERE last_active_at < now() - interval '14 days'"
    )
    db.commit()
```

That's the entire job — `ON DELETE CASCADE` on `user_checkins.session_id`, `conversation_turns.session_id`, `user_memory_summary.session_id`, and (transitively) `evaluator_scores.checkin_id` means one `DELETE` on `user_sessions` cleans up every table that references it, with no risk of the job deleting from one table and missing another as the schema grows. **There's no audio table to clean up** — per §5, raw voice is never written anywhere in the first place, so there's nothing there for this job to even reach.

Two details worth being deliberate about:
- **The window resets on activity.** `last_active_at` updates on every turn (§7), so "2 weeks" means 2 weeks *since the last time this person used the app*, not 2 weeks from first visit. A daily user's data never expires; someone who visits once has it cleaned up 2 weeks later. This seems like the right reading of "clean up after 2 weeks," but confirm it's what you actually meant before shipping it — the alternative (fixed 2-week expiry regardless of activity) is a one-line change (`created_at` instead of `last_active_at`) if that's what you want instead.
- **The cookie's `max_age` and the job's `interval '14 days'` have to move together.** They're independent settings in two different places that encode the same policy — if you change one without the other, the browser might present a cookie for a session Postgres has already deleted (handled fine, §7 re-issues in that case) or the reverse, a session lingers in Postgres after the browser's cookie already expired (harmless, cleaned up on the next day's run either way). Worth a code comment linking the two so a future edit doesn't silently desync them.

**Why APScheduler and not Celery**: Celery (+ Redis or RabbitMQ as a broker) is the standard answer for background jobs in Python, but it's a second service to run and operate for what is currently one daily job and one periodic Summarizer. APScheduler running inside the same FastAPI process costs nothing extra to deploy. Revisit this if job volume or complexity grows — none of which is true yet.

---

## 10. Telemetry — Langfuse

The point of this, stated plainly since it's easy to skip when things seem to work: an LLM pipeline fails silently far more often than it crashes. A bad retrieval, a prompt that drifted, a stage that's slower than it should be — none of that throws an exception, it just quietly produces a worse response. Telemetry is how you see that happening instead of finding out from a bad screenshot someone sends you later.

**Why Langfuse over the originally-planned Phoenix**: both are free at this project's scale (Langfuse Cloud's Hobby tier: 50,000 units/month, 30-day retention, no card required; Phoenix Cloud's AX Free tier: 25,000 spans/month, 15-day retention). The deciding factors were fit, not cost — Langfuse's session view groups every span under one `bandhu_sid` across a multi-turn conversation (a closer match to a chatbot than trace-by-trace), and its scores view maps directly onto stage 12's sampled Evaluator. Phoenix's dedicated retrieval-span rendering was the one place it had a real edge, but that's just a few structured attributes on the span either way (see the retrieval example below) — not worth losing the other two for. Full reasoning trail is in the conversation that produced this doc, kept here so a future re-evaluation isn't starting from scratch.

**Setup**: Langfuse Cloud accepts standard OpenTelemetry traces over OTLP, so the same OpenInference `AnthropicInstrumentor` used for Phoenix works unchanged — only the exporter destination changes:

```python
import base64
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.anthropic import AnthropicInstrumentor

auth = base64.b64encode(
    f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
).decode()

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(
        endpoint="https://cloud.langfuse.com/api/public/otel/v1/traces",
        headers={"Authorization": f"Basic {auth}"},
    ))
)
AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
```

`AnthropicInstrumentor` wraps every call made through the `anthropic` SDK client automatically — once instrumented, every Claude call in Classify/Orchestrator/Generate/Summarizer/Evaluator shows up in Langfuse with prompt, response, token counts, and latency, with no manual span code needed at each call site. **Verify the exact OTLP endpoint, region, and auth header format against Langfuse's current docs before implementing** — same caveat as everywhere else in this doc, package APIs and endpoints move.

**What doesn't come free — needs a manual span**: Postgres queries and STT/TTS calls aren't LLM calls made through the `anthropic` SDK, so there's no auto-instrumentor covering them. Wrap each:

```python
from opentelemetry import trace
tracer = trace.get_tracer("bandhu.pipeline")

def transcribe(audio_bytes):
    with tracer.start_as_current_span("stt") as span:
        result = stt_client.transcribe(audio_bytes)
        span.set_attribute("stt.detected_language", result.language)
        span.set_attribute("stt.duration_seconds", result.duration)
        return result
```

The retrieval stage is the same pattern, with structured attributes standing in for Phoenix's dedicated retrieval panel:

```python
def retrieve(query_embedding, filters):
    with tracer.start_as_current_span("retrieval") as span:
        results = vector_search(query_embedding, filters)
        span.set_attribute("retrieval.result_count", len(results))
        span.set_attribute("retrieval.entry_keys", [r.entry_key for r in results])
        span.set_attribute("retrieval.top_similarity", results[0].similarity if results else 0)
        return results
```

Doing this for every non-LLM stage (Safety gate, Memory read, Eligibility gate, Retrieval, Memory write, STT, TTS) means a single trace in Langfuse shows the *entire* turn — not just the Claude calls in it, but what was retrieved, what the Orchestrator decided, and for a voice turn, exactly how long transcription and synthesis each took. That's the piece that actually lets you tell, later, whether a slow voice reply was Claude's fault or the STT/TTS provider's.

**Content control — what actually leaves the server**: `AnthropicInstrumentor` captures full prompt and completion text by default, which for this app means raw conversation content by default going to a third-party cloud service. That's the wrong default for a mental-health check-in product. `TelemetryConfig` (in `app/config.py`, same pattern as `Settings`) splits what's logged into two tiers: metadata — stage name, latency, token counts, model, `session_id`, error info — always logs; raw message/prompt/retrieval-content fields are opt-in per field, off unless explicitly turned on. This needs to be enforced at the span-creation call sites (strip or redact the relevant attribute before `span.set_attribute` when the corresponding config flag is off), not just a note in this doc.

**Open gap — `session_id` and retention**: Langfuse's 30-day retention window is longer than this project's own 14-day cleanup guarantee (`user_sessions` cascade-delete, §9). If `session_id` reaches Langfuse in any span, a person's data can outlive its promised deletion window by up to 16 days in that one system. Not resolved yet — options are hashing/truncating `session_id` before it's attached to a span (closes the gap, but breaks Langfuse's session-grouping view, which needs a stable literal id) or documenting this as an accepted exception. Tracked in §14.

**Sampling**: the Sampled evaluator (stage 12, 5–10% of responses) is a separate concept from telemetry — tracing covers every request, the evaluator scores a sample of them against the MITI rubric. Don't conflate "we trace it" with "we score it"; tracing is observability (did this work correctly, technically), evaluation is quality (was this a *good* response). Both matter, for different questions.

---

## 11. Suggested project layout

```
backend/
  app/
    main.py                    # FastAPI app, middleware registration, router mounting
    creations.py                # §12 — separate from pipeline/, its own write path
    breathe.py                  # §13 — direct content query, bypasses pipeline/ entirely
    listen.py                   # §13 — direct content query, bypasses pipeline/ entirely
    middleware/
      session.py                # §7 — cookie issuance/validation
      rate_limit.py              # §8 — slowapi config
    pipeline/
      orchestrator.py            # runs the 12 stages in sequence, handles the branches
      stages/
        ingest.py                 # §4 stage 1 — calls clients/stt.py for audio turns
        safety_gate.py
        classify.py
        memory_read.py            # §2 — reads both memory horizons
        eligibility_gate.py
        retrieval.py
        orchestrator_judgment.py  # the LLM-discretion stage itself, named distinctly from
                                    # pipeline/orchestrator.py (the sequencer) to avoid confusion
        generate.py                # §6 — assembles system/messages from both horizons
        guardrail_check.py
        memory_write.py            # §2, §5 — writes conversation_turns + user_checkins,
                                    # calls clients/tts.py for voice turns
      summarizer.py               # stage 11, async
      evaluator.py                # stage 12, async, sampled
    clients/
      claude.py                   # thin wrapper over the anthropic SDK, model-tier config from
                                    # vector-database.md §1 lives here
      voyage.py
      stt.py                       # §5 — transcribe + discard, provider TBD
      tts.py                       # §5 — synthesize, provider TBD
      storage.py                   # §12/§13 — Supabase Storage client, image creations + audio tracks
      db.py                       # SQLAlchemy session/engine setup — the one client that talks
                                    # to Supabase, for both content and user tables
    models/                       # SQLAlchemy table classes — mirrors vector-database.md §2
      user_sessions.py
      conversation_turns.py       # §2
      user_checkins.py
      user_creations.py           # §12
      audio_tracks.py              # §13
      user_memory_summary.py
      evaluator_scores.py
      redirect_templates.py
      safety_patterns.py
      helplines.py
    jobs/
      cleanup.py                  # §9
      scheduler.py                 # APScheduler wiring for cleanup.py + summarizer.py
    telemetry/
      langfuse_setup.py           # §10
  alembic/                        # migration history
  tests/
    pipeline/                     # one test module per stage — each stage is a plain function,
                                    # so each is unit-testable without spinning up FastAPI at all
  requirements.txt / pyproject.toml
```

The thing worth internalizing from this layout as you build it: **every stage in `pipeline/stages/` is a plain Python function that takes typed input and returns typed output** — no stage reaches into a global session or the request object directly. That's what makes `pipeline/orchestrator.py` a readable sequence of calls instead of a tangle, and it's what makes each stage testable in isolation (feed it a fixture, assert the output) rather than needing a running server to test anything.

---

## 12. Creations — image and poem

Not part of the check-in pipeline's 12 stages — this is a separate feature (the "Co-Create" screen) with its own write path, that later feeds *into* the pipeline via the Summarizer (stage 11, §4), the same way `user_checkins` does. **Music was originally in scope here too — corrected**: what `ux-flow.html` calls "Listen" turned out to be Bandhu-provided curated audio, not something the person creates, which is a different enough feature to move to its own section — see §13.

**Two Home-screen buttons, one flow**: "Write Together" and "Poem" both lead here — they're two entry points into the same `user_creations` write path, not two separate features. No schema or backend implication, just worth knowing so nothing gets built twice.

**Write path**: person creates something → normalize by type:
- **Poem** — plain text, goes straight into `user_creations.text_content` (`vector-database.md` §2). No storage bucket involved.
- **Image** — binary file, uploaded to a Supabase Storage bucket; `user_creations.storage_path` stores the path, not the file.
- Either way, a `caption` gets written alongside it — a short description of what the thing is, not the thing itself.

**Why a caption, not the raw content, is what Summarizer reads**: same principle as `conversation_turns` vs. `user_memory_summary` in §2 — the long-term narrative should carry an impression ("wrote something about feeling stuck this week"), never a replay of someone's actual creative work. This is also what keeps the Summarizer's Claude call cheap and bounded — a caption is a sentence, a poem or an image is not.

**Retention**: same 14-day window as everything else — `user_creations.session_id` cascades from `user_sessions` (`vector-database.md` §2) like every other user table. No special lifecycle, per your call — this isn't treated as more permanent than a check-in.

**Storage cleanup gap, worth naming**: the cleanup job (§10) deletes the `user_creations` *row* via cascade, but that doesn't automatically delete the *file* sitting in the Supabase Storage bucket — Postgres cascades don't reach into object storage. Left as an open item (§14) rather than solved here, since the fix (a small job that deletes orphaned storage objects, or a Supabase Storage lifecycle rule) is worth its own decision, not a guess bolted onto this section.

**Still an open README-level question**: `ux-flow.html` itself flags Co-Create as "additive, scope risk — ship in v1, or wait for the core loop to be validated first." Schema and write path exist now per your explicit call to build them, but that doesn't resolve the underlying product question — worth a real decision before this reaches real users, not just an implementation.

---

## 13. Direct-entry features — Breathe and Listen

Two more Home-screen buttons that, like Creations, sit outside the 12-stage check-in pipeline — but for a different reason: the person is asking for something directly, not sending a message that needs Classify/Safety-gate/Orchestrator judgment at all. Building these as pipeline stages would be modeling a decision nobody needs to make.

### Breathe

Tapping "Breathe" on Home requests a grounding/breathing exercise directly — no message, no mood tag, no Claude call needed, because the person already said what they want by tapping the button.

- **Query**: same `content_entries` table Retrieval (§4 stage 6) already uses, filtered to `category = 'grounding-technique'`, no vector similarity involved since there's no message to embed — just a plain `WHERE` + a rotation so the same entry doesn't show every time (`ORDER BY random()` is fine at this corpus size; revisit only if the library grows large enough for it to matter).
- **Logging**: still worth a lightweight `user_checkins` row (`theme = 'breathing'`, `is_help_offer = false` since the person asked rather than being offered) — this is what lets the Summarizer's "bigger picture" include "did a breathing exercise" the same way it would a Creation, which is the actual thing that prompted this section to exist.
- **The real blocker, already logged and easy to lose track of**: `knowledge-base/OPEN_QUESTIONS.md` already flags that no breathing/relaxation script has been sourced — mhGAP explicitly doesn't cover this, and it points to a separate WHO manual ("Problem Management Plus") that hasn't been fetched. This backend path can be fully built and still have nothing real to serve until that content gap closes. Worth stating plainly so "the Breathe button works" doesn't get confused with "there's something good behind it."

### Listen

Tapping "Listen" requests curated audio — this is Bandhu offering something, not the person creating anything, which is why it's a different table (`audio_tracks`, `vector-database.md` §2) and a different flow from Creations, not a variant of it.

- **Query**: filter `audio_tracks` by `mood_tags` against whatever mood context is available (the long-term summary or the most recent `user_checkins.mood_tag`, if there is one) — and a sensible default set if there isn't, since Listen is reachable with zero prior check-ins.
- **No Claude call needed** for the basic version — this is a filtered lookup against a small curated table, same shape as `redirect_templates`.
- **Not written into `user_creations`** — the person didn't make anything. Whether a "listened to X" fact is worth logging to `user_checkins` for Summarizer context is a smaller, genuinely open version of the same question Breathe answers yes to — flagged in §14, not decided.
- **The real blocker**: nobody has sourced or licensed any actual tracks yet (`vector-database.md` §5) — same shape of gap as Breathe's missing content, just a rights/curation problem instead of a source-material one.
- **Also an open README-level question**, same as Creations: `ux-flow.html` flags Listen as "additive, scope risk," not a confirmed v1 feature.

---

## 14. Open items

- **STT and TTS providers are unresolved** (§1, §5) — needs evaluation against real Hindi/Hinglish audio before locking in, same posture as the embedding provider decision. Don't guess a specific model/API shape until that's done.
- **Voice duration cap (60–90s, §5) is a starting guess**, not validated.
- **Voice latency — accept it or stream TTS (§5)** — named as a real UX question, not decided. Affects how complex the TTS integration needs to be for v1.
- **`conversation_turns`' read-time window (2 hours / last 12 rows) is a starting guess** (§2), not validated — same posture as the rate-limit numbers below.
- **`slowapi`'s rate-limit numbers (§8) are starting guesses**, not validated against real usage patterns.
- **Whether the Summarizer (stage 11) runs via APScheduler or is triggered inline during Memory write** is still the same open decision flagged in both `pipeline.html` and `vector-database.md` — this doc assumes "periodic via APScheduler" as the default but doesn't lock it in.
- **The 2-week cleanup window's reset-on-activity behavior (§9)** needs an explicit yes/no from you — currently written as "resets on every turn," the more natural reading, but the one-line alternative is noted if that's wrong.
- **Hybrid search (`vector-database.md` §3) is written but not wired in** — add it only if pure vector search is ever observed missing an exact-phrase match. Don't build it preemptively.
- **No auth today, but `models/user_sessions.py` should stay additive-friendly** if that ever changes (`vector-database.md` §2 already notes this at the schema level) — worth keeping in mind while writing the session middleware too, so adding a login path later doesn't require rewriting how `session_id` is issued, just adding an optional `account_id` alongside it.
- **`pipeline.html`'s "Safety gate needs conversation memory" finding is resolved by §2 above** — that doc's Open Items section has been updated to point here instead of describing it as unsolved.
- **`user_creations.caption` — who writes it, isn't decided** (§12, also logged in `vector-database.md` §5). The person typing their own short description, versus a Claude call generating one automatically, are genuinely different builds — the second needs a Claude call in the creation write path that doesn't exist yet.
- **Deleting a `user_creations` row doesn't delete its file from Supabase Storage** (§12) — the 14-day cascade only reaches Postgres rows. Needs either a small periodic job to clean up orphaned storage objects, or a Storage-level lifecycle rule, once one is chosen.
- **No breathing/relaxation content exists yet** (§13) — the backend path can be fully built with nothing real behind it. Same content gap already logged in `knowledge-base/OPEN_QUESTIONS.md`, just easy to lose track of once the backend "works."
- **No audio tracks sourced or licensed for Listen** (§13, `vector-database.md` §5) — a content/rights question, not a schema one.
- **Whether a "listened to X" fact belongs in `user_checkins` for Summarizer context isn't decided** (§13) — smaller version of the same question Breathe already answers yes to.
- **Co-Create and Listen are both still an open README-level product decision** (§12, §13, `docs/ux-flow.html`) — ship in v1, or wait for the core loop to validate first. Building the backend for both doesn't resolve this; it just means the decision is now the only thing blocking either from shipping.
- **`session_id` in Langfuse spans outlives the 14-day cleanup guarantee** (§10) — Langfuse's 30-day retention means a person's `session_id` can exist there up to 16 days after its row is deleted from `user_sessions`. Not resolved: hash/truncate `session_id` before it's attached to a span (closes the gap, breaks Langfuse's session-grouping view) versus documenting this as an accepted exception.
- **Retrieval cache (§4 stage 6) — deferred, not dropped.** `rag-components.html` (an earlier doc, predating the single-Supabase pivot) proposed a Redis/Upstash cache in front of `pgvector`, sized to "skip both the embedding call and the pgvector query" on a near-duplicate check-in. That combination doesn't actually hold: detecting a *near*-duplicate requires embedding the incoming message first to compare it, so a similarity-threshold cache can only skip the `pgvector` query, not the embedding call. Two different caches, if this is ever built: an **exact-text cache** (hash the raw message, skip embedding entirely on a literal repeat) and a **similarity cache** (skip only the `pgvector` query once the embedding already exists). Not worth building now — no traffic volume yet to justify another external service, same tradeoff already declined for Celery/Redis (§10, §9). Revisit once real Voyage embedding-call costs are visible.
