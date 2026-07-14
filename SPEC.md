# Product Spec — v2
## Bandhu — A light, companion-based mental health check-in app

Prototype Link - https://stitch.withgoogle.com/projects/1054452762569491480

> This is the original product spec/vision doc — written before most of the implementation below existed. It's kept as-is for the reasoning behind the product's shape; it's a vision doc, not a changelog, so specific tech choices mentioned (or not mentioned) here may have since diverged from what's actually built. For current implementation status, see the root [README.md](README.md), [docs/](docs/index.html), and [frontend/README.md](frontend/README.md).

---

## 1. The core need (why this, why now)

Mental health has a reach problem, not just an access problem. Existing solutions fail on different axes:

- **Wysa** — clinically strong, but feels like a therapy app. Effective, but the CBT-exercise framing keeps it "heavy."
- **Tele MANAS / MANAS / KIRAN** (government) — right intent, poor execution. Rule-based, glitchy, or understaffed. Concept isn't the gap; follow-through is.
- **Juno / HeyJuno** (global) — closest to the tone we want (companion, journaling, gentle), but not built for India — no vernacular depth, no local crisis infrastructure, no understanding of India's collectivist, stigma-heavy context.

**The actual gap:** something that feels like texting a friend, not opening a treatment tool. Available in different languages. Anonymous by default. Cheap or free. And light enough that a person with zero energy left in the day can still use it for 10 seconds.

---

## 2. How the app approaches the user

**Framing:** This is not "an app for your mental health." It's a companion you check in with — closer in spirit to texting someone who remembers you, than to opening a wellness dashboard.

**First interaction:** No sign-up friction, no clinical intake form, no "rate your anxiety 1-10." Just: *"What's on your mind?"* — text, or a fast mood tap if typing feels like too much.

**Ongoing interaction shape, every time — "open door, not a fork":**
1. Acknowledge what the person shared — briefly, warmly, in plain language. This is the whole response by default. Nothing else is required to make the screen feel complete.
2. Below the acknowledgment, a small, quiet, easy-to-ignore option appears — never a decision the person has to make before moving on. Two forms this can take, shown only when relevant:
   - *"Want something to try?"* → opens one grounding technique or reframe from the vetted content library.
   - *"I noticed a thought in there — want to look at it together?"* → the thinking-trap flow (see below), shown only when the mood is genuinely negative, never on every message.
3. If the person doesn't tap anything, the screen still needs to look and feel finished — deliberate whitespace, not an unfinished task.
4. Stop. No forced follow-up, no "let's dig deeper" unless the person asks.

**Spot the thinking trap (new):**
- Only offered, never forced, and only when the shared content suggests a distorted thought pattern (catastrophizing, all-or-nothing thinking, mind-reading, etc.) — this is a CBT self-help concept, not a diagnosis, and must be framed that way.
- The app names **one** possible pattern at a time, phrased as a guess, never a fact — e.g. *"This sounds a little like assuming the worst — does that feel true, or not quite?"*
- The person can reject it outright ("not quite") and the app accepts that immediately, no follow-up pressure. Wrong-until-confirmed-right is the default stance.

**Closing the loop (new):**
- Any time a suggestion is taken (grounding exercise, poem, music, thinking-trap check), the *next* relevant check-in can reference it — *"Last time, you tried the morning breathing while feeling anxious — did that help, even a little?"*
- This question is itself optional (thumbs up/down or skip) — never a required step before the person can check in again.
- The purpose is twofold: it's what makes the memory feel like care rather than tracking, and it quietly tells the system what's actually helping this specific person, without needing a complex recommendation engine.

**Tone rules:**
- Never diagnostic ("you seem anxious" → no). Descriptive instead ("sounds like a heavy day").
- Never therapy-speak or jargon.
- Memory is used to show care, not to prove tracking — e.g. referencing something earlier only when it's actually relevant, never as a "here's your data" recap.

---

## 3. What it will do

- Let a person check in via short text, voice-to-text, or an image, whenever they want, in their own language.
- Respond with warmth, brevity, and (when relevant) one grounding technique or reframing prompt pulled from a vetted content library — not freely generated advice.
- Quietly build a light pattern-memory over time (moods, recurring themes) to make future check-ins feel like they're building on the last one.
- Detect concerning language through a separate, rules-based safety layer and immediately surface real human help — helplines, counseling networks — clearly and without friction.
- Be anonymous by default. No real name required to use the core companion.
- Work on low-end phones and patchy connectivity (this shapes the tech choices, not just the product).
- Generate a plain-language, purely descriptive "notes for your doctor" export from check-in history (dates, mood patterns, physical symptoms mentioned in the user's own words) — a bridge to real medical help, with zero interpretation by the AI.
- Gently and optionally name a possible "thinking trap" (a CBT self-help concept, not a diagnosis) when a shared thought suggests one — always framed as a guess the person can reject, never a verdict.
- Follow up on a suggestion taken in an earlier check-in, asking (optionally) whether it helped — closing the loop rather than letting each interaction be disconnected from the last.

---

## 4. What it will NOT do

- **Not diagnose.** Ever. No clinical labels, no "you have depression." (Naming a *thinking pattern*, like "this sounds like assuming the worst," is different from labeling a *disorder* — the former is offered as a guess and dropped the moment the person disagrees; the latter never happens at all.)
- **Not replace therapy or a doctor.** It's a companion and a bridge to real help, not a substitute for either.
- **Not generate open-ended emotional advice from the raw model.** All substantive guidance is retrieved from a vetted, human-reviewed content library — the model's job is tone, not content invention.
- **Not gamify with streaks, points, or leaderboards.** These create guilt when broken — directly opposed to "light."
- **Not require daily use to "work."** No punishing the person for coming back after a week away.
- **Not sell or share user data**, or use conversations to train any model.
- **Not attempt to handle a genuine crisis alone.** The safety layer's only job in that moment is to hand off to real human help, fast, without the AI trying to "manage" it.
- **Not interpret medical records, lab values, or symptoms.** No document-upload pathway for medical records feeds the AI at all — this is a hard architectural exclusion, not just a prompt instruction. Mood-and-physical-health correlation is a real, valid question, but it's answered by redirecting to a doctor, never by the model reasoning over the person's actual health data.
- **Not give advice on major life decisions** (leaving a relationship, quitting a job, legal disputes) as if it has judgment on the person's specific situation — it can help someone think out loud, but won't tell them what to do.
- **Not respond to "do I have [disorder]" with a yes/no or a label**, even informally — redirect to what a professional evaluation involves instead.
- **Not treat itself as a replacement for human relationships.** If a person signals the app is becoming their primary source of connection, it says so plainly and gently points back toward people in their life, rather than leaning into the dependency.
- **Not knowingly serve users under a set minimum age without a distinct, more conservative safety mode** — this needs a deliberate policy decision before launch, not a default assumption either way.

---

## 5. What makes it feel light

- **One primary action per screen.** No nav bar with five tabs.
- **Every interaction resolvable in under ~10-15 seconds** if the person wants that — depth is optional, never required.
- **No progress bars, no broken streaks, no guilt mechanics.**
- **Responses are short by design** — a rule enforced at the guardrail level, not just a writing preference.
- **No forced categorization of feelings** — a person can vent without needing to name the emotion first.
- **Visual and copy tone reads calm and human**, not clinical-blue, not corporate-wellness.
- **Memory shows up as care** ("that sounds like it's been sitting with you since last week") rather than as a tracked metric.

---

## 6. How this is different from what's already out there

| | Wysa | Govt. tools (Tele MANAS/MANAS) | Juno/HeyJuno | **This product** |
|---|---|---|---|---|
| Core framing | CBT exercise tool | Crisis routing / mood tracker | Journaling companion | Companion-first check-in |
| India-native language depth | Partial (Hindi added) | Yes, but clunky execution | No | Yes, from day one |
| Distribution | App + WhatsApp | WhatsApp + calls | App only | PWA + WhatsApp |
| Tone | Therapeutic | Bureaucratic/rule-based | Warm, but US/global default | Warm, India-contextual |
| Memory | Session-based | None | Journal-based recall | Light pattern-memory, care-framed |
| Guardrails on generation | Unclear/proprietary | Rule-based only | Unclear | Explicit RAG + guardrails, crisis layer fully separate |
| Cost to user | Freemium | Free (govt) | Subscription | Free/near-free by design |

**The actual differentiation isn't a single feature** — it's the combination: Juno's warmth + Wysa's clinical grounding + government tools' free distribution intent, minus each of their specific failure modes (US-centric tone, clinical heaviness, poor execution).

---

## 7. Edge case scenarios (boundary moments the product must handle deliberately)

These are the moments where the "acknowledge → one step → stop" pattern isn't enough on its own — each needs an explicit rule, because the natural LLM response tends to overstep.

**"Is my mood from my health, or something else?" (medical doubt)**
- Never interpret symptoms or records. Acknowledge the question as valid in general terms, then offer the doctor's-notes export as the concrete next step. No document upload pathway feeds the AI.

**"Should I leave my partner / quit my job / take legal action?" (major life decisions)**
- The companion can reflect what the person has said back to them, or ask what they're weighing — but never recommends a course of action. The line: help someone think, don't think for them.

**"Do I have depression / anxiety / bipolar / [disorder]?"**
- Never confirm or deny. Respond with what a professional evaluation actually involves, and offer to help find one, rather than answering the question as asked.

**"You're the only one I can talk to" / signs of emotional dependency**
- Don't reinforce it, even warmly. State plainly that the app isn't a substitute for people in their life, while staying warm — not a cold refusal, but not agreement either.

**User is a minor (or age is unknown/unverified)**
- Requires a deliberate, more conservative mode: no crisis content left ambiguous, tighter escalation thresholds, no romantic/dependency-coded companion framing under any circumstance. This needs a real policy decision, not a default.

**User downplays a genuine crisis** ("I'm fine, just thinking about it" after concerning language)
- The rules-based detector should key on the concerning phrase itself, not the reassurance that follows it. Escalation copy shown once is enough — don't repeatedly re-trigger it in the same conversation if the person has already seen it, but never suppress it on a first true positive because of hedging language.

**User asks for medication information** (dosage, interactions, "should I take more/less")
- Hard redirect to a doctor/pharmacist every time. No exceptions, regardless of how the question is framed.

---

## 8. UI screens — role of each, and what's changing from the current build

Reference: the current Bandhu build already has 9 screens. Below is each one's job, and what needs to change to match the principles above.

**Welcome** — *Keep as-is.* Sets trust before asking for anything: "A companion, not a treatment tool," privacy stated plainly, no feature tour, no permissions grab.

**Home** — *Needs rebalancing.* Currently three floating action buttons (Breathe / Write Together / Listen) sit at equal visual weight next to the text input — reads as a features menu before the person has said anything. Change: the text input ("Share how you're feeling...") becomes the single dominant element on the screen. Breathe/Write Together/Listen move to secondary weight — smaller, lower, or reachable from the bottom nav rather than floating on the entry screen.

**Response** — *The core change.* Currently shows the acknowledgment plus an immediate two-button card ("Not right now" / "Yes, let's try") — a fork the person has to resolve before continuing. Change: show only the acknowledgment first, full attention, nothing competing with it. Below it, a small, muted, easy-to-ignore line — *"want something to try?"* and, when relevant, *"I noticed a thought in there — want to look at it together?"* — never styled as a mandatory decision. If tapped, the suggestion appears beneath the acknowledgment, never replacing it. If ignored, the screen still needs deliberate whitespace so it reads as finished, not incomplete.

**Thinking trap (new screen, branches from Response)** — One possible pattern named at a time, phrased as a guess with an easy "not quite" / "yeah, that's it" choice. Never a list of distortions, never framed as analysis of the person.

**Co-Create (shared poem)** — *Keep, but flag as scope risk.* On-brand and warm, but additive rather than core loop. Worth deciding explicitly whether this ships in the 2-month v1 or waits for a validated core loop first.

**Listen (ambient soundscapes)** — Same flag as Co-Create — lovely, but additive. Same scope decision applies.

**Immersive breathing (full-screen "Breathe out...")** — *Keep as-is.* One focused action, full screen, one-tap exit ("Stay as long as you need") — matches the "single focused action" principle for anything reached via an opt-in tap.

**Looking Back** — *Keep as-is, and extend.* Descriptive daily lines instead of a mood graph — exactly the "care, not data" pattern. Extend it to include the closing-the-loop follow-up: referencing whether a past suggestion (breathing, poem, thinking trap) actually helped, not just what mood was logged.

**Crisis Support** — *Keep as-is.* Deliberately different from the rest of the app's tone — direct, real numbers, Call Now / WhatsApp, zero AI cleverness. This is the one screen where "different on purpose" is correct.

**Settings/Privacy** — *Keep as-is.* Clear language toggle, real "Delete My Data," privacy stated plainly, not buried.

---

## Open questions to resolve before build
- Exact language rollout order (Hindi first, then which regional languages?)
- Whether image-mood-input launches at MVP or v2 (currently slated for weeks 5-6)
- Legal/compliance posture under India's DPDP Act — needs a real pass before any user data is stored
- Whether Co-Create and Listen ship in the 2-month v1, or wait until the core loop (check-in → response → optional suggestion → optional thinking-trap → follow-up) is validated with real users
- Thinking-trap detection: rules-based keyword triggers first, or wait until enough real check-in data exists to do this reliably
