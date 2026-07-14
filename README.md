# [Bandhu](https://bandhu-companion.netlify.app/)

A companion-first mental health check-in app for India — texting a friend, not opening a treatment tool.

> **Status: Prototype.** Solo project, built incrementally and end-to-end functional (real backend, real database, real deployed frontend), but not reviewed or launched as a product. Safety-critical content (crisis-language detection, clinical suggestions) is gated behind an explicit self-vetted/professional-reviewed pipeline — see [Known gaps](#known-gaps) before treating anything here as production-ready.

**Live:**
- Frontend — https://bandhu-companion.netlify.app
- Backend — https://bandhu-0j9q.onrender.com (`/health`)

**Read next:**
- [SPEC.md](SPEC.md) — the original product spec: why this, why now, what it will/won't do
- [docs/index.html](docs/index.html) — engineering docs: pipeline design, backend architecture, vector DB schema, UX flow, manual QA test cases
- [frontend/README.md](frontend/README.md) — what's actually built on the frontend, and its known gaps in detail

---

## Repo layout

```
bandhu/
  backend/            FastAPI + SQLAlchemy async + Postgres/pgvector
    app/              pipeline stages, models, clients (NVIDIA NIM, Langfuse)
    alembic/          migrations
    scripts/          content ingestion, local-only seed scripts
  frontend/           React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui
    src/routes/       Home, Response, Thinking Trap, Breathing, Looking Back, Crisis Support, Settings
  docs/               engineering + product design docs (HTML + Markdown)
  knowledge-base/      vetted content library + safety patterns (VETTING.md governs what can be ingested)
  render.yaml         backend deploy config (Render)
  frontend/netlify.toml  frontend deploy config (Netlify)
```

## Quickstart (local dev)

**Backend** — needs Python 3.12, [`uv`](https://docs.astral.sh/uv/), and a Postgres database with the `pgvector` extension enabled (Supabase's free tier is what's actually used in prod; a local Dockerized Postgres works fine for dev too):

```bash
cd backend
cp .env.example .env   # fill in DATABASE_URL, NVIDIA_API_KEY, LANGFUSE_* keys
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

**Frontend** — needs Node:

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173/ (Welcome), /privacy/, and /app/ (SPA) — backend must be running on :8000
```

See `backend/.env.example` for every environment variable the backend reads, and `frontend/README.md` for why the frontend has three separate HTML entry points instead of one SPA shell.

## Known gaps

The full, honest list lives in [frontend/README.md § Known gaps](frontend/README.md#known-gaps-stated-plainly) — crisis-pattern seeding is local-testing-only, voice input isn't wired, some product-spec features (Co-Create, Listen) aren't built yet. Read it before assuming a given flow is launch-ready.
