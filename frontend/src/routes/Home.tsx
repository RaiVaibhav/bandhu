import { useState } from "react";
import { useNavigate } from "react-router";
import { Mic } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { MoodTapRow, type Mood } from "@/components/bandhu/MoodTapRow";
import { SecondaryActionsRow } from "@/components/bandhu/SecondaryActionsRow";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { runMockPipeline } from "@/lib/mockPipeline";

// Served from public/mascot — a plain URL, not a module import, since
// files under public/ are copied verbatim rather than bundled by Vite.
const MASCOT_CLOUD_URL = "/mascot/mascot-cloud.jpg";

export default function Home() {
  const navigate = useNavigate();
  const [message, setMessage] = useState("");
  const [mood, setMood] = useState<Mood | null>(null);

  // A mood tap alone (no text) is a valid, complete check-in — see
  // pipeline.html's "mood-tap only" stress-test case.
  const canShare = message.trim().length > 0 || mood !== null;

  function handleShare() {
    if (!canShare) return;
    const result = runMockPipeline(message, mood);
    navigate("/response", { state: { message, ...result } });
  }

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <AppHeader />

      <main className="flex flex-1 flex-col justify-between gap-stack-md px-edge-mobile pb-stack-md">
        <div className="flex flex-col items-center gap-2 pt-2 text-center">
          <img
            src={MASCOT_CLOUD_URL}
            alt=""
            className="size-16 rounded-full object-cover shadow-sm"
          />
          <MoodTapRow value={mood} onChange={setMood} />
        </div>

        {/* The one dominant thing on screen — see docs/ux-flow.html. */}
        <div className="flex flex-col gap-3">
          <div className="claymorphic-card flex flex-col gap-3 p-4">
            <Textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Share how you're feeling…"
              className="min-h-24 resize-none border-none bg-transparent p-0 text-base shadow-none focus-visible:ring-0"
            />
            <div className="flex items-center justify-between">
              <Mic className="size-5 text-muted-foreground" aria-hidden />
              <Button
                size="lg"
                className="rounded-full px-6"
                disabled={!canShare}
                onClick={handleShare}
              >
                Share
              </Button>
            </div>
          </div>

          <SecondaryActionsRow />

          {/* Dev-only design preview — real crisis detection is backend
              logic (app/pipeline/stages/safety_gate.py) not wired to this
              UI-only pass yet. Never rendered in a production build. */}
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
