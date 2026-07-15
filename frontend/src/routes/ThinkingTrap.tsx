import { useState } from "react";
import { useNavigate } from "react-router";
import { CheckCircle2, Loader2 } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { Button } from "@/components/ui/button";
import { ApiError, sendThinkingTrapSelection } from "@/lib/apiClient";
import { cn } from "@/lib/utils";

// The real 8 entries from knowledge-base/vetted/thinking-traps.md
// (tt-001..tt-008) — Burns' cognitive distortion taxonomy, self-vetted at
// the appropriate medium risk tier (VETTING.md). Copied verbatim, not
// reworded for this screen — this IS the vetted wording. icon paths are the
// real per-pattern claymorphic icons from Stitch's "Spot the Thinking
// Traps (Expanded)" mockup, downloaded to public/thinking-traps/ rather
// than hotlinked — same convention as public/mascot/.
const PATTERNS = [
  { key: "tt-001", label: "All-or-Nothing Thinking", text: "Seeing things as only good or bad, with no middle ground.", icon: "/thinking-traps/tt-001-all-or-nothing.jpg" },
  { key: "tt-002", label: "Fortune Telling", text: "Predicting things will turn out badly without evidence.", icon: "/thinking-traps/tt-002-fortune-telling.jpg" },
  { key: "tt-003", label: "Mind Reading", text: "Assuming you know what others are thinking about you.", icon: "/thinking-traps/tt-003-mind-reading.jpg" },
  { key: "tt-004", label: "Emotional Reasoning", text: "Believing that because you feel a certain way, it must be true.", icon: "/thinking-traps/tt-004-emotional-reasoning.jpg" },
  { key: "tt-005", label: "Blaming Others", text: "Putting all the blame on someone else and ignoring your own role.", icon: "/thinking-traps/tt-005-blaming-others.jpg" },
  { key: "tt-006", label: "Overgeneralizing", text: "Seeing a single negative event as a never-ending pattern of defeat.", icon: "/thinking-traps/tt-006-overgeneralizing.jpg" },
  { key: "tt-007", label: "Labeling", text: "Assigning a rigid, negative label to yourself or others based on one instance.", icon: "/thinking-traps/tt-007-labeling.jpg" },
  { key: "tt-008", label: "Discounting the Positives", text: 'Rejecting positive experiences by insisting they "don\'t count."', icon: "/thinking-traps/tt-008-discounting-positives.jpg" },
];

/** Opens only after the quiet "want to look at it together?" is accepted
 * (Response.tsx) — see docs/ux-flow.html: "the app doesn't diagnose a
 * single pattern — it offers a small set of plain-language options so the
 * person names what they're feeling." Single-select: pipeline.html
 * describes the person naming one pattern, which then drives one tailored
 * reply, not a multi-select checklist.
 *
 * Calls the real Thinking Trap re-entry (POST /thinking-trap) — bypasses
 * Classify/Eligibility/Orchestrator entirely, since the person already
 * named their own pattern; Generate gets a dedicated directive
 * (thinking_trap_followup) instructed to go deeper than the usual one-line
 * acknowledgment, using that exact pattern's real vetted content, not a
 * client-side text hack re-run through the generic pipeline. */
export default function ThinkingTrap() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleContinue() {
    const pattern = PATTERNS.find((p) => p.key === selected);
    if (!pattern || isSubmitting) return;

    setIsSubmitting(true);
    setError(null);
    try {
      const result = await sendThinkingTrapSelection(pattern.key);
      navigate("/response", {
        state: { message: `I think I might be doing this: "${pattern.text}"`, response: result.response },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong — mind trying again?");
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex h-svh flex-col bg-background">
      <AppHeader back="/response" />

      <main className="flex min-h-0 flex-1 flex-col gap-stack-md overflow-hidden px-edge-mobile pb-stack-lg">
        <div className="flex flex-col gap-1 pt-1">
          <h1 className="font-heading text-lg font-semibold text-foreground">What does this feel like?</h1>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Pick whichever one lands closest — there's no wrong answer here.
          </p>
        </div>

        {/* A plain stacked block, not a flex column — flexbox's default
            shrink would otherwise compress each row below its own content
            height to fit the scroll container, clipping text instead of
            actually scrolling. min-h-0 + overflow-y-auto here still scroll
            the same way; only the layout mode (flex vs. block) changes. */}
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto py-1">
          {PATTERNS.map((p) => (
            <div
              key={p.key}
              onClick={() => setSelected(p.key)}
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-xl border-2 bg-card p-2.5 shadow-sm transition-colors",
                selected === p.key ? "border-primary/60 bg-primary/5" : "border-transparent",
              )}
            >
              <img
                src={p.icon}
                alt=""
                className="size-14 shrink-0 rounded-lg bg-muted object-cover"
              />
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <p className="text-sm font-medium text-foreground">{p.label}</p>
                <p className="text-xs text-muted-foreground leading-snug">{p.text}</p>
              </div>
              <CheckCircle2
                className={cn(
                  "size-6 shrink-0 text-primary transition-opacity",
                  selected === p.key ? "opacity-100" : "opacity-0",
                )}
              />
            </div>
          ))}
        </div>

        {error && (
          <div className="flex items-center justify-between gap-3 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <span>{error}</span>
            <button type="button" onClick={handleContinue} className="shrink-0 font-medium underline">
              Retry
            </button>
          </div>
        )}

        <Button
          size="lg"
          className="shrink-0 rounded-full"
          disabled={!selected || isSubmitting}
          onClick={handleContinue}
        >
          {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : "Continue"}
        </Button>
      </main>
    </div>
  );
}
