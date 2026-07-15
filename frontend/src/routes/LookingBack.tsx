import { useEffect, useState } from "react";
import { Cloud, Loader2, Minus, Sun } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { ApiError, getLookingBack, type LookingBackResponse } from "@/lib/apiClient";
import { cn } from "@/lib/utils";

const COLD_START_TEXT = "Nothing to look back on yet — check in a few times and a picture will start to form here.";

type Tone = "heavy" | "neutral" | "light";

// mood_tag isn't a fixed enum — MoodTapRow's four taps (low/anxious/okay/
// good) only cover the mood-tap shortcut. Most real check-ins are free
// text, and Classify's own prompt (backend/app/pipeline/stages/classify.py)
// deliberately asks for open-vocabulary "one or two words for emotional
// tone" ("anxious", "sad", "stressed", "flat", or whatever else genuinely
// fits) — so a small exact-match lookup would silently miss most of what
// people actually type. This does substring matching against a broader,
// curated word list instead; anything not recognized honestly falls back
// to neutral rather than guessing at a valence it can't support.
const HEAVY_WORDS = [
  "low", "anxious", "sad", "stressed", "overwhelmed", "worried", "afraid", "scared",
  "angry", "frustrated", "upset", "hopeless", "exhausted", "tired", "lonely", "guilty",
  "ashamed", "hurt", "heavy", "down", "depress", "numb", "flat", "empty", "disappointed",
  "nervous", "panick", "irritable", "grief",
];
const LIGHT_WORDS = [
  "good", "happy", "relieved", "calm", "hopeful", "content", "grateful", "excited",
  "proud", "peaceful", "fine", "better", "light", "joy", "optimistic", "okay",
];

function classifyValence(moodTag: string | null): Tone | null {
  if (!moodTag) return null;
  const lowered = moodTag.toLowerCase();
  if (HEAVY_WORDS.some((w) => lowered.includes(w))) return "heavy";
  if (LIGHT_WORDS.some((w) => lowered.includes(w))) return "light";
  return null;
}

// The timeline's icon/color/shape language, ported from Stitch's "Looking
// Back" mockup (its "heavy / neutral / light day" framing) — three
// buckets, matching the mockup's own three icons (cloud / horizontal_rule
// / sun), not one per literal mood word. Organic, asymmetric border-radii
// (not a plain rounded-xl) are copied as-is from the mockup's claymorphic
// blob shapes.
const TONE_STYLE: Record<Tone, { icon: typeof Cloud; bg: string; dot: string; blob: string }> = {
  heavy: { icon: Cloud, bg: "bg-evening-lavender", dot: "bg-tertiary", blob: "rounded-[40px_24px_32px_16px]" },
  neutral: { icon: Minus, bg: "bg-card", dot: "bg-muted-foreground/50", blob: "rounded-[24px_40px_16px_32px]" },
  light: { icon: Sun, bg: "bg-mint-calm", dot: "bg-primary/70", blob: "rounded-[32px_24px_40px_24px]" },
};

// The overall tone the whole screen washes toward — the same heavy/
// neutral/light language each day's own card uses, applied once at the
// aggregate level. Derived from the real mood_tags people's messages were
// actually classified as, not from parsing the free-form Summarizer prose
// for sentiment, which would be guessing at a meaning the text may not
// literally carry.
function deriveTone(checkins: LookingBackResponse["checkins"]): Tone {
  let heavy = 0;
  let light = 0;
  for (const c of checkins) {
    const valence = classifyValence(c.mood_tag);
    if (valence === "heavy") heavy += 1;
    else if (valence === "light") light += 1;
  }
  if (heavy > light) return "heavy";
  if (light > heavy) return "light";
  return "neutral";
}

// The Summarizer (stage 11) is a nightly batch job — a brand-new session,
// or one it just hasn't reached yet, genuinely has no narrative written
// for it. Rather than a flat "nothing here" line sitting above a timeline
// that clearly does have entries, this builds one honest sentence
// straight from the same real mood_tags the timeline itself renders —
// no invented narrative, just an aggregate of facts already on screen.
function buildFallbackSummary(checkins: LookingBackResponse["checkins"], tone: Tone): string {
  const dayCount = new Set(checkins.map((c) => c.date)).size;
  const dayWord = dayCount === 1 ? "day" : "days";
  const toneClause =
    tone === "heavy" ? ", leaning toward heavier days" : tone === "light" ? ", leaning toward lighter days" : "";
  return `You've checked in on ${dayCount} ${dayWord} recently${toneClause}.`;
}

// Bare "YYYY-MM-DD" parsed as local calendar date, not through the ISO
// string constructor — `new Date("YYYY-MM-DD")` parses as UTC midnight,
// which can display as the previous day in timezones behind UTC.
function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

function groupByDate(checkins: LookingBackResponse["checkins"]) {
  const byDate = new Map<string, LookingBackResponse["checkins"]>();
  for (const c of checkins) {
    const existing = byDate.get(c.date);
    if (existing) existing.push(c);
    else byDate.set(c.date, [c]);
  }
  return [...byDate.entries()];
}

/** ux-flow.html: "Opens with one line summarizing the week... then the
 * daily timeline underneath as supporting detail, not the other way
 * around. No charts, no streaks." summary_text is the Summarizer's (stage
 * 11) rolling narrative — nightly batch job, so a brand-new session
 * genuinely has nothing here yet; that's a real cold start, not a loading
 * bug. */
export default function LookingBack() {
  const [data, setData] = useState<LookingBackResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLookingBack()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Couldn't load this right now.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const tone = data ? deriveTone(data.checkins) : "neutral";

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <AppHeader back="/" />

      <main className="flex flex-1 flex-col gap-stack-md px-edge-mobile pb-stack-lg">
        <h1 className="font-heading text-xl font-semibold text-primary">Looking Back</h1>

        {isLoading && (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {data && (
          <>
            {data.checkins.length === 0 ? (
              <p className="text-sm leading-relaxed text-muted-foreground">{COLD_START_TEXT}</p>
            ) : (
              <div className={cn("rounded-2xl p-4 shadow-sm", TONE_STYLE[tone].bg)}>
                <p className="text-sm leading-relaxed text-foreground">
                  {data.summary_text ?? buildFallbackSummary(data.checkins, tone)}
                </p>
              </div>
            )}

            {/* Vertical timeline — the connecting line, dot, and organic
                "claymorphic blob" card shapes are ported from Stitch's
                "Looking Back" mockup; per-day text stays the real
                mood_tag/theme facts the backend actually returns rather than
                the mockup's own invented narrative sentences ("Felt heavy,
                you noted feeling overwhelmed...") — Bandhu never fabricates
                content the person didn't actually provide. */}
            {data.checkins.length > 0 && (
              <div className="relative flex flex-col gap-3 pl-6 before:absolute before:inset-y-2 before:left-[5px] before:w-px before:bg-border">
                {groupByDate(data.checkins).map(([date, entries]) => {
                  const style = TONE_STYLE[classifyValence(entries[0]?.mood_tag ?? null) ?? "neutral"];
                  const Icon = style.icon;
                  return (
                    <div key={date} className="relative">
                      <div className={cn("absolute -left-6 top-5 size-2.5 rounded-full ring-4 ring-background", style.dot)} />
                      <div className={cn("flex flex-col gap-1 p-4 shadow-sm", style.bg, style.blob)}>
                        <div className="flex items-center gap-2">
                          <Icon className="size-4 text-foreground/70" />
                          <p className="text-sm font-semibold text-foreground">{formatDate(date)}</p>
                        </div>
                        {entries.map((e, i) => (
                          <p key={i} className="text-xs text-muted-foreground">
                            {[e.mood_tag, e.theme].filter(Boolean).join(" · ") || "Checked in"}
                          </p>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
