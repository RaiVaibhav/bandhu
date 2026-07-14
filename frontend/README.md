# Bandhu — frontend

Mobile-focused web app. React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui, themed with tokens extracted directly from the Stitch prototype — see `DESIGN_SYSTEM.md` for exactly where each value came from.

**Status: connected to the real backend.** `src/lib/apiClient.ts` calls the FastAPI backend's real `POST /message` (`../backend`) — no more mock pipeline. Requires the backend running locally (`cd ../backend && uv run uvicorn app.main:app --reload --port 8000`) with a real `DATABASE_URL` — see `../backend/README.md` / the root of this repo for local Postgres setup via Docker. `credentials: "include"` on the fetch call is required for the `bandhu_sid` session cookie to survive cross-origin; the backend's `CORSMiddleware` (`app/main.py`) is scoped to `http://localhost:5173`/`:4173` specifically, not `*`, since a credentialed cookie and a wildcard origin can't coexist.

Real backend response shape is a single blended string per turn (`{ response, crisis, helplines }`) — each reply renders as one chat bubble, with no separate "help offer" field to render as its own tappable line, since Generate produces one warm reply, not two structurally separate pieces (see `backend/app/pipeline/stages/generate.py`). Response is a real multi-turn thread, though, not a single reply-and-done screen — see below.

## Why two HTML entry points, not one SPA shell

```
frontend/
  index.html          # Welcome — static, real page load, no React
  privacy/
    index.html          # Privacy Policy — also static, linked from Welcome's consent checkbox
  app/
    index.html          # SPA mount point
  src/
    welcome/             # Welcome's own tiny vanilla-JS entry (no framework)
    privacy/              # Privacy Policy's entry (just pulls in the shared stylesheet)
    main.tsx              # React entry, mounted into app/index.html
    routes/                # Home, Response, Crisis Support
    components/
      ui/                  # shadcn/ui, re-themed
      bandhu/               # bespoke: AppHeader, ChatBubble, MoodTapRow, ...
```

Welcome is genuinely outside the React app — a first-open-only landing gate (`docs/ux-flow.html`: "First open only... every later visit starts here instead" at Home). The inline `<script>` in `index.html`'s `<head>` checks `localStorage.bandhu_visited` + `bandhu_consent_version` and redirects to `/app/` *before paint*, so a returning visitor never sees Welcome flash before landing on Home. Everything after "Say hello" — Home, Response, Crisis Support — is one React Router SPA mounted at `/app/`, `basename="/app"`.

Vite's multi-page build (`vite.config.ts`'s `rollupOptions.input`) produces `dist/index.html`, `dist/privacy/index.html`, and `dist/app/index.html` as independent entry bundles from one toolchain — one `package.json`, one dev server, three real pages.

## Age gate + consent

Welcome has a required checkbox — "I'm 13 or older, and I've read the Privacy Policy" — that gates the "Say hello" button (disabled until checked). Accepting sets two `localStorage` keys: `bandhu_visited` and `bandhu_consent_version`. The version is a literal (`"1"`, duplicated in both `index.html`'s inline head script and `src/welcome/main.ts` — they have to move together) so that a future change to the age minimum or the Privacy Policy's substance can force re-consent just by bumping the constant in both places, rather than silently grandfathering everyone who already clicked through an older version.

**Stated plainly, this is a self-declaration, not verification** — there's no ID check, and 13+ was a product decision made without the backend having any actual minor-specific handling (a distinct crisis-resource list, stricter guardrails) built yet — `docs/backend-architecture.md`'s "Minor / age-unknown session flag" open item is still unresolved. The Privacy Policy itself says this plainly rather than implying more safety infrastructure exists than actually does.

The Privacy Policy (`privacy/index.html`) is a first draft grounded in what the backend actually does today (anonymous session cookie, 14-day retention, NVIDIA NIM/Supabase/Langfuse as processors, no accounts) — explicitly marked as not lawyer-reviewed, same "self-vetted, not professional-reviewed" posture `knowledge-base/VETTING.md` uses for clinical content. It has a placeholder where a real contact email/address needs to go before this is shown to anyone outside testing.

## What's built

The core spine (`docs/ux-flow.html`): **Welcome → Home → Response**, **Crisis Support**, plus the branches that came after: **Thinking Trap** (opens from Response's "Want to look at it together?" line; real 8 patterns from `knowledge-base/vetted/thinking-traps.md`, ingested into `content_entries` via `backend/scripts/ingest_content.py`; picking one calls a dedicated `POST /thinking-trap` — bypasses Classify/Eligibility/Orchestrator entirely and gives Generate a distinct directive instructed to go deeper than the usual one-line acknowledgment, not a client-side text bridge through the generic pipeline), **Breathing** (full-screen, visual treatment ported from Stitch's "Immersive Breathing Experience" mockup, spoken phase cues via browser `SpeechSynthesis`, logs a real `user_checkins` row via `POST /breathe`), **Looking Back** (real Summarizer narrative + per-day timeline via `GET /looking-back`), and **Settings** (language-preference toggle, real "delete my data" via `DELETE /session`, link to the Privacy Policy). Looking Back and Settings are reached from two icon buttons in Home's header (`AppHeader`'s `menu` prop) — there's no bottom nav built, so this is the actual persistent entry point for now, not a stand-in for one.

**Home's visual design was ported from Stitch's "Home Experience (Reimagined)" iteration** (not the plainer earlier pass, not "Home (Evolved)"'s four-button menu) — floating mascot with an ambient breathing glow behind it, small floating "pebble" buttons (only Breathe links anywhere real), a pill-style input. The input still stays the one dominant interactive element per `docs/ux-flow.html` — the pebbles are atmospheric, not a menu competing for attention before the person has said anything.

Still not built: Co-Create (Poem), Listen (Music) — both are an open README-level product decision (ship in v1 or wait), not just unbuilt UI. Home's floating pebbles show their entry points as inert placeholders, not links to nothing.

**One known Stitch/spec mismatch was deliberately NOT replicated** (per `docs/ux-flow.html`'s own "doesn't match the current Stitch build yet" section, confirmed before building):
- **Response** is a real back-and-forth thread — an acknowledgment plus at most one muted, ignorable line per turn, never a two-button "Not right now / Yes, let's try" decision card in Stitch's `response.html` mockup. The Stitch mockup is a visual reference for bubble/tone styling only, not a literal "one reply and the screen is done" spec — Response keeps an open composer so the person can keep talking, same session, same backend memory, turn after turn.

**Crisis Support** uses the real, dial-confirmed helpline numbers from `knowledge-base/safety/helpline-directory.md` (verified 2026-07-13), not Stitch's mockup numbers. No WhatsApp link — the directory only confirms these connect by voice call, not that a WhatsApp number exists for them.

## Commands

```bash
npm run dev       # http://localhost:5173/ (Welcome), /privacy/, and /app/ (SPA)
npm run build     # type-checks, then builds dist/index.html + dist/privacy/index.html + dist/app/index.html
npm run preview   # serve the production build locally
```

## Known gaps, stated plainly

- **Crisis detection can fire locally, but only against a self-vetted seed list** — `safety_patterns` ships empty by default (`vector-database.md` §4's ingestion gate correctly blocks `self-vetted` content from this high-risk table until professional review happens); `backend/scripts/seed_safety_patterns.py` is a deliberate, loudly-labeled local-only bypass so the real flow can be exercised before that review happens. Never run it against a shared/deployed database. Matching is exact substring, not fuzzy — see the script's own phrase list before assuming a given message should trigger it.
- **Mood-tap-only check-ins are bridged client-side** — the real backend's `POST /message` only accepts free text, no distinct mood field (`pipeline.html`'s own open item: "Ingest needs a distinct non-text branch"). `Home.tsx`'s `MOOD_ONLY_TEXT` turns a bare mood tap into a plain sentence before sending it — a frontend shim standing in for backend work that doesn't exist yet.
- **Mic icon on Home is decorative only** — not a real button, no voice input wired. Real speech-to-text needs a provider decision (backend/app/pipeline/stages/ingest.py already raises clearly for voice input rather than pretending to support it) — a larger scoped piece of work, not a quick fix, and not done in this pass. Breathing's spoken phase cues (browser `SpeechSynthesis`, text-to-speech) are unrelated and already real — don't conflate the two directions.
- **Static hosting's SPA rewrite for `/app/*`** is configured in this package's `netlify.toml` for Netlify specifically — a different host (GitHub Pages, etc.) would need the equivalent rule written its own way.
- **No automated tests** — this pass was verified via `tsc -b` (clean), `vite build` (clean), and HTTP-level route checks (dev + preview, all 200) — not a visual/browser check. Look at it in an actual mobile-width browser before treating any screen as final.
- **Privacy Policy has a placeholder contact** — the "Questions" section just says to add a real email/contact before this is shown to anyone outside testing. Not filled in automatically, since that's a real decision about what to expose publicly.
- **Most `offer_suggestion` turns still aren't a separate tappable card** — Generate weaves most suggestions directly into the reply text itself (see `backend/app/pipeline/stages/generate.py`), so Response doesn't render anything extra for them. The one exception: a breathing invitation (`bt-001`) gets its own "Try it now" line into the real Breathing screen, the same way `notice_thinking_trap` gets "Want to look at it together?" — both lead somewhere real to tap into, unlike a generic suggestion that's already fully said inline.
- **Settings' language toggle doesn't translate anything yet** — it only remembers a preference in `localStorage`; no i18n library is wired up.
