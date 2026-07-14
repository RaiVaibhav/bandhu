import { useLocation, useNavigate } from "react-router";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { ChatBubble } from "@/components/bandhu/ChatBubble";

type ResponseState = {
  message?: string;
  acknowledgment?: string;
  helpOfferLine?: string | null;
};

// Shown when this route is opened directly (no state, e.g. a page
// refresh) so the screen is still a valid, complete stopping point on its
// own — see docs/ux-flow.html: "every screen above has a valid ending."
const FALLBACK_ACKNOWLEDGMENT = "I hear you. That sounds like a lot to carry.";

export default function Response() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = (location.state ?? {}) as ResponseState;
  const acknowledgment = state.acknowledgment ?? FALLBACK_ACKNOWLEDGMENT;

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <AppHeader back />

      <main className="flex flex-1 flex-col justify-center gap-4 px-edge-mobile pb-stack-lg">
        <ChatBubble>{acknowledgment}</ChatBubble>

        {/* At most one small, muted, easy-to-ignore line — never a
            two-button decision card. See docs/ux-flow.html's corrected
            spec, and backend/app/pipeline/stages/orchestrator_judgment.py
            for the real directive this stands in for. */}
        {state.helpOfferLine && (
          <button
            type="button"
            className="self-start pl-1 text-sm text-muted-foreground underline decoration-muted-foreground/40 underline-offset-4 transition-colors hover:text-foreground"
          >
            {state.helpOfferLine}
          </button>
        )}

        <button
          type="button"
          onClick={() => navigate("/")}
          className="mt-8 self-center text-xs text-muted-foreground/70"
        >
          Back to Home
        </button>
      </main>
    </div>
  );
}
