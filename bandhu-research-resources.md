# Bandhu — Research Resources & RAG Guidelines

Reference doc for grounding the RAG content library and tone evaluator.
Feed this to Claude Code as project context when building the corpus/retrieval pipeline.

---

## Part 1 — Content library sources (grounds *what* the app says)

These are the sources to build/adapt the vetted corpus from. Do not copy text directly —
paraphrase and adapt into short, warm, plain-language entries, ideally with a counselor
review pass before production use.

| Source | What it is | Why it's useful here |
|---|---|---|
| **WHO mhGAP Intervention Guide** | WHO's official guide for delivering mental health support via non-specialists, not clinicians. Free, CC BY-NC-SA licensed. | Core framework for *what to say* — step-by-step, plain-language support techniques, not clinical theory. |
| **NIMHANS manuals** (Handbook for Lay Counsellors, Suicide Prevention handbook) | India's national mental health institute's own training material for non-professionals. | India-specific tone, examples, and cultural context already built in. |
| **NIMHANS MindNotes app** | A live self-help app NIMHANS already built — five sections including a 7-module self-help library (Managing Self-Criticality, Mastering Worry, Behavioural Activation, Calming & Soothing, Managing Negative Thoughts, Mastering Anger, Managing Social Anxiety). | Reference implementation — study its phrasing, flow, and question style directly. |
| **NHS self-help booklets** (UK) | Public, plain-language mental health workbooks published by NHS trusts. | Good for tone/phrasing reference — how professionals write for a general (non-clinical) audience. |
| **EmpatheticDialogues** (Meta/FAIR, GitHub: `facebookresearch/EmpatheticDialogues`) | ~25,000 crowd-sourced conversations pairing a situation with an empathetic reply. CC-BY-4.0. | Large example set of "what a good empathetic reply sounds like" across many emotions. |
| **ESConv** (GitHub: `thu-coai/Emotional-Support-Conversation`) | ~1,300 dialogues where each supporter turn is labeled with the support strategy used (question, reflection, validation, suggestion, etc.), based on Hill's Helping Skills Theory. | More directly useful than EmpatheticDialogues — the strategy labels map well to your acknowledge → offer → stop pattern. |

---

## Part 2 — Tone / warmth / bias evaluation sources (grounds *how well* the response lands)

| Source | What it is | Why it's useful here |
|---|---|---|
| **MITI Coding Manual (v4.2/4.2.1)** | The Motivational Interviewing Treatment Integrity scale — the real rubric researchers use to score how well a counselor is doing MI (reflection-to-question ratio, open questions %, MI-adherent vs non-adherent statements). Free PDF at `motivationalinterviewing.org`. | The direct basis for an automated tone-evaluator rubric — turns "warm and non-directive" into scoreable dimensions. |
| **CASAA MITI resource page** (`casaa.unm.edu/tools/miti.html`) | Real transcripts already coded against the MITI scale. | Calibration set — compare your own evaluator's scores against known-correct human scoring. |
| **"Benchmarking Motivational Interviewing Competence of Large Language Models"** (academic paper) | Prior research applying MITI scoring specifically to LLM-generated responses — clinicians coded a set of AI transcripts against the manual. | Validates this exact approach and shows a real pipeline for doing it. |

---

## RAG design guidelines (keeping context useful without inflating cost)

**Chunking**
- Corpus entries stay short — 1-3 sentences each, not paragraphs pulled wholesale from source documents. The output guardrail already caps responses at ~60 words, so larger chunks are wasted tokens.

**Retrieval**
- Pre-filter by metadata (emotion tag, category, intensity, language) *before* running vector similarity search — shrinks the search space and keeps results relevant without needing a large `top_k`.
- Retrieve top 2-3 matches maximum. More matches doesn't improve quality here — the product principle is "one small offer, not a list," so retrieving few, highly relevant chunks is both cheaper and more correct.

**Embeddings**
- Embed the corpus once, store vectors in pgvector, query repeatedly — don't re-embed the corpus per request.
- Each user check-in needs exactly one small embedding call (the incoming text) — trivially cheap regardless of provider.

**Caching**
- Cache embedding + retrieval results (Redis/Upstash) for common/similar incoming messages, with a similarity threshold to reuse cached results instead of re-embedding near-duplicate check-ins.

**Memory / context injection**
- Only inject the structured light-memory summary (a few lines) into the prompt — never raw conversation history or a growing transcript, which is the biggest hidden cost trap as usage grows.

**Model selection**
- Use a fast/cheap model for the phrasing step (acknowledge + phrase one retrieved chunk — a small task).
- Reserve the tone evaluator (MITI-based LLM-as-judge) for a sampled percentage of responses (e.g. 5-10%) for ongoing quality monitoring, not every single message.

**Rough cost shape per check-in, once wired this way:** one small embedding call (near-free) + one filtered pgvector query (near-free) + one short capped-length LLM call (cheap) + occasional sampled evaluator call. The corpus itself stays nearly free to maintain regardless of size — the per-request LLM call is the number that actually needs watching as usage grows.
