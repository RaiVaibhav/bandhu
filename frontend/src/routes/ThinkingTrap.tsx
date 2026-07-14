import { useState } from "react";
import { useNavigate } from "react-router";
import { Loader2 } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, sendThinkingTrapSelection } from "@/lib/apiClient";
import { cn } from "@/lib/utils";

// The real 8 entries from knowledge-base/vetted/thinking-traps.md
// (tt-001..tt-008) — Burns' cognitive distortion taxonomy, self-vetted at
// the appropriate medium risk tier (VETTING.md). Copied verbatim, not
// reworded for this screen — this IS the vetted wording.
const PATTERNS = [
  { key: "tt-001", label: "All-or-Nothing Thinking", text: "Seeing things as only good or bad, with no middle ground." },
  { key: "tt-002", label: "Fortune Telling", text: "Predicting things will turn out badly without evidence." },
  { key: "tt-003", label: "Mind Reading", text: "Assuming you know what others are thinking about you." },
  { key: "tt-004", label: "Emotional Reasoning", text: "Believing that because you feel a certain way, it must be true." },
  { key: "tt-005", label: "Blaming Others", text: "Putting all the blame on someone else and ignoring your own role." },
  { key: "tt-006", label: "Overgeneralizing", text: "Seeing a single negative event as a never-ending pattern of defeat." },
  { key: "tt-007", label: "Labeling", text: "Assigning a rigid, negative label to yourself or others based on one instance." },
  { key: "tt-008", label: "Discounting the Positives", text: 'Rejecting positive experiences by insisting they "don\'t count."' },
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
    <div className="flex min-h-svh flex-col bg-background">
      <AppHeader back />

      <main className="flex flex-1 flex-col gap-stack-md px-edge-mobile pb-stack-lg">
        <div className="flex flex-col gap-2">
          <h1 className="font-heading text-xl font-semibold text-foreground">What does this feel like?</h1>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Pick whichever one lands closest — there's no wrong answer here.
          </p>
        </div>

        <div className="flex flex-col gap-2.5">
          {PATTERNS.map((p) => (
            <Card
              key={p.key}
              onClick={() => setSelected(p.key)}
              className={cn(
                "cursor-pointer border-l-4 py-3 transition-colors",
                selected === p.key ? "border-l-primary bg-primary/5" : "border-l-transparent",
              )}
            >
              <CardContent className="flex flex-col gap-0.5">
                <p className="font-medium text-foreground">{p.label}</p>
                <p className="text-xs text-muted-foreground leading-relaxed">{p.text}</p>
              </CardContent>
            </Card>
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
          className="rounded-full"
          disabled={!selected || isSubmitting}
          onClick={handleContinue}
        >
          {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : "Continue"}
        </Button>
      </main>
    </div>
  );
}
