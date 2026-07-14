# Bandhu — frontend

Mobile-focused web app. React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui, themed with tokens extracted directly from the Stitch prototype — see `DESIGN_SYSTEM.md` for exactly where each value came from.

**Status: UI only.** No backend wiring yet — `src/lib/mockPipeline.ts` stands in for a real `POST /message` call to the FastAPI backend (`../backend`). Replace that module once the two are wired together; nothing else in `src/routes/` should need to change, since it already treats the pipeline result as an opaque `{ acknowledgment, helpOfferLine }` shape.

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

## What's built (core spine only)

Per `docs/ux-flow.html`, the path most check-ins actually take: **Welcome → Home → Response**, plus **Crisis Support** (the one branch too safety-critical to leave unbuilt). Not yet built: Thinking Trap, Looking Back, Settings, Breathing (full-screen), Co-Create (Poem), Listen (Music) — `SecondaryActionsRow` on Home shows their entry points as inert placeholders, not links to nothing.

**Two known Stitch/spec mismatches were deliberately NOT replicated** (per `docs/ux-flow.html`'s own "doesn't match the current Stitch build yet" section, confirmed before building):
- **Response** is a single acknowledgment + at most one muted, ignorable line — not the two-button "Not right now / Yes, let's try" decision card in Stitch's `response.html` mockup.
- **Home** keeps the message input as the one dominant element — not the four prominent suggestion buttons in Stitch's "Home (Evolved)" iteration.

**Crisis Support** uses the real, dial-confirmed helpline numbers from `knowledge-base/safety/helpline-directory.md` (verified 2026-07-13), not Stitch's mockup numbers. No WhatsApp link — the directory only confirms these connect by voice call, not that a WhatsApp number exists for them.

## Commands

```bash
npm run dev       # http://localhost:5173/ (Welcome), /privacy/, and /app/ (SPA)
npm run build     # type-checks, then builds dist/index.html + dist/privacy/index.html + dist/app/index.html
npm run preview   # serve the production build locally
```

## Known gaps, stated plainly

- **No backend wiring** — `mockPipeline.ts` fabricates a plausible acknowledgment/help-offer client-side from simple heuristics (message length, mood). It is not the real Orchestrator (`backend/app/pipeline/orchestrator.py`).
- **No real crisis-detection trigger** — Crisis Support is reachable via a dev-only preview link on Home (`import.meta.env.DEV`, stripped from production builds), since Safety gate detection lives entirely in the backend and isn't called from this UI yet.
- **Mic icon on Home is decorative only** — not a real button, no voice input wired. Matches the backend's own posture: STT/TTS providers are still unresolved (`docs/backend-architecture.md` §1/§5).
- **Static hosting needs an SPA rewrite rule for `/app/*`** — `vite preview` and the Vite dev server both fall back to `app/index.html` for unmatched sub-paths (`/app/response`, `/app/crisis`) automatically; a real static host (Netlify, GitHub Pages, etc.) needs an explicit rewrite rule doing the same, or a direct link/refresh on those routes will 404. Not configured yet — pick a host before wiring this.
- **No automated tests** — this pass was verified via `tsc -b` (clean), `vite build` (clean), and HTTP-level route checks (dev + preview, all 200) — not a visual/browser check. Look at it in an actual mobile-width browser before treating any screen as final; I have not done that myself.
- **Privacy Policy has a placeholder contact** — the "Questions" section just says to add a real email/contact before this is shown to anyone outside testing. Not filled in automatically, since that's a real decision about what to expose publicly.
- **No link to the Privacy Policy from inside the SPA itself** — only reachable from Welcome's consent checkbox right now. It belongs on the Settings screen too (`docs/ux-flow.html`'s "Settings / Privacy"), which isn't built yet.
