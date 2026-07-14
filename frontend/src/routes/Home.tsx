import { useState } from "react";
import { useNavigate } from "react-router";
import { Loader2, PenLine, Music, Send, Wind } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { MoodTapRow, type Mood } from "@/components/bandhu/MoodTapRow";
import { ApiError, sendMessage } from "@/lib/apiClient";
import { cn } from "@/lib/utils";

// Served from public/mascot — a plain URL, not a module import, since
// files under public/ are copied verbatim rather than bundled by Vite.
const MASCOT_CLOUD_URL = "/mascot/mascot-cloud.jpg";

// The real backend only accepts free-text (POST /message's body is just
// {text}) — there's no distinct mood-tap field yet server-side.
// pipeline.html's own open item ("Ingest needs a distinct non-text branch
// feeding the same spine") is still unresolved, so a mood-only check-in is
// bridged into a plain sentence here rather than waiting on that backend
// work. This is a client-side stand-in, not a real Ingest capability.
const MOOD_ONLY_TEXT: Record<Mood, string> = {
  low: "I'm feeling low today.",
  anxious: "I'm feeling anxious today.",
  okay: "I'm feeling okay today.",
  good: "I'm feeling good today.",
};

// Only "Breathe" links anywhere real — Co-Create and Listen are still an
// open README-level product decision (ship in v1 or wait), and neither has
// real content behind it yet, so they stay decorative rather than linking
// somewhere half-built. Positions/animation delays match Stitch's "Home
// Experience (Reimagined)" mockup (frontend/DESIGN_SYSTEM.md).
const PEBBLES = [
  { icon: Wind, label: "Breathe", path: "/breathe", position: "top-[8%] left-[2%]", anim: "animate-pebble-1", bg: "bg-white" },
  { icon: PenLine, label: "Write Together", path: null, position: "top-[18%] right-[0%]", anim: "animate-pebble-2", bg: "bg-evening-lavender" },
  { icon: Music, label: "Listen", path: null, position: "bottom-[12%] right-[6%]", anim: "animate-pebble-3", bg: "bg-mint-calm" },
];

/** Home Experience (Reimagined) — ported from the real Stitch mockup, not
 * the earlier plainer pass (see frontend/DESIGN_SYSTEM.md). The floating
 * pebbles are ambient/atmospheric around the mascot, not a menu row
 * competing with the input for attention — docs/ux-flow.html's "input
 * stays dominant" principle still holds, this is a visual treatment, not a
 * button-first redesign. */
export default function Home() {
  const navigate = useNavigate();
  const [message, setMessage] = useState("");
  const [mood, setMood] = useState<Mood | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A mood tap alone (no text) is a valid, complete check-in — see
  // pipeline.html's "mood-tap only" stress-test case.
  const canShare = !isSubmitting && (message.trim().length > 0 || mood !== null);

  async function handleShare() {
    if (!canShare) return;
    const textToSend = message.trim() || (mood ? MOOD_ONLY_TEXT[mood] : "");
    if (!textToSend) return;

    setIsSubmitting(true);
    setError(null);
    try {
      const result = await sendMessage(textToSend);
      if (result.crisis) {
        navigate("/crisis", { state: { helplines: result.helplines } });
        return;
      }
      navigate("/response", {
        state: {
          message: textToSend,
          response: result.response,
          helpOfferType: result.help_offer_type,
          suggestionEntryKey: result.suggestion_entry_key,
        },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong — mind trying again?");
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <AppHeader menu />

      <main className="relative flex flex-1 flex-col items-center justify-center px-edge-mobile pb-stack-md">
        {/* Breathing background glow — purely atmospheric, sits behind everything */}
        <div className="organic-bg pointer-events-none absolute left-1/2 top-1/2 -z-10 h-[150%] w-[150%] -translate-x-1/2 -translate-y-1/2 rounded-full" />

        <div className="relative mb-stack-md flex aspect-square w-full max-w-[280px] animate-float items-center justify-center">
          <div className="absolute bottom-4 h-16 w-3/4 rounded-full bg-primary/20 blur-2xl" />
          <img
            src={MASCOT_CLOUD_URL}
            alt=""
            className="h-full w-full max-h-56 max-w-56 rounded-full object-cover shadow-xl"
          />

          {PEBBLES.map(({ icon: Icon, label, path, position, anim, bg }) => (
            <button
              key={label}
              type="button"
              disabled={!path}
              onClick={() => path && navigate(path)}
              className={cn(
                "pebble absolute flex aspect-square w-[72px] flex-col items-center justify-center gap-1 rounded-2xl border border-secondary/10 p-3 shadow-sm transition-transform disabled:cursor-default",
                position,
                anim,
                bg,
              )}
            >
              <Icon className="size-6 text-primary" />
              <span className="text-center text-[10px] font-medium leading-tight text-earth-text">{label}</span>
            </button>
          ))}
        </div>

        <MoodTapRow value={mood} onChange={setMood} />

        <div className="mt-stack-md flex w-full flex-col items-center gap-2">
          <p className="text-sm italic text-secondary/70">I'm here to listen…</p>

          <div className="relative w-full max-w-md">
            <input
              type="text"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleShare();
              }}
              placeholder="Share how you're feeling…"
              disabled={isSubmitting}
              className="w-full rounded-full border-none bg-white/60 py-4 pl-6 pr-14 text-base shadow-sm backdrop-blur-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
            <button
              type="button"
              onClick={handleShare}
              disabled={!canShare}
              aria-label="Share"
              className="absolute right-2 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
            </button>
          </div>

          {error && (
            <div className="flex w-full max-w-md items-center justify-between gap-3 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <span>{error}</span>
              <button type="button" onClick={handleShare} className="shrink-0 font-medium underline">
                Retry
              </button>
            </div>
          )}

          {/* Dev-only design preview — real crisis detection is backend
              logic (app/pipeline/stages/safety_gate.py); safety_patterns
              only has the local, self-vetted seed list until professional
              review happens (vector-database.md §4). Never rendered in a
              production build. */}
          {import.meta.env.DEV && (
            <button
              type="button"
              onClick={() => navigate("/crisis")}
              className="self-center text-[10.5px] text-muted-foreground/50 underline"
            >
              View Crisis Support (design preview)
            </button>
          )}
        </div>
      </main>
    </div>
  );
}
