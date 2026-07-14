import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { Loader2, Mic } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { ChatBubble } from "@/components/bandhu/ChatBubble";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, getConversation, sendMessage } from "@/lib/apiClient";

type ResponseState = {
  message?: string;
  response?: string;
  helpOfferType?: string | null;
  suggestionEntryKey?: string | null;
};

type Turn = {
  role: "user" | "bot";
  text: string;
  helpOfferType?: string | null;
  suggestionEntryKey?: string | null;
};

// Shown when this route is opened directly (no state, e.g. a page
// refresh) so the screen is still a valid, complete stopping point on its
// own — see docs/ux-flow.html: "every screen above has a valid ending."
const FALLBACK_RESPONSE = "I hear you. That sounds like a lot to carry.";

// Only "notice_thinking_trap" needs its own tappable follow-through —
// Generate deliberately withholds the specific pattern name for that tool
// ("that comes later, only if they opt in"), unlike most "offer_suggestion"
// turns, which are already woven into the reply text itself (generate.py).
// See docs/ux-flow.html: "at most one small, muted, easy-to-ignore line."
const QUIET_LINE_TEXT = "Want to look at it together?";

// The one offer_suggestion exception: a breathing invitation (bt-*,
// knowledge-base/vetted/breathing-invitation.md) leads somewhere real to
// tap into — the actual built Breathing screen — so it gets its own quiet
// line the same way notice_thinking_trap does, instead of staying purely
// inline text with nothing to follow through on.
const BREATHE_LINE_TEXT = "Try it now";

/** Response is a real companion conversation, not a single reply that ends
 * things (docs/ux-flow.html: "a real companion conversation... turn after
 * turn"). Home hands off the first exchange via router state; every turn
 * after that happens right here, same session, same backend memory. */
export default function Response() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = (location.state ?? {}) as ResponseState;

  const [turns, setTurns] = useState<Turn[]>(() => {
    const seeded: Turn[] = [];
    if (state.message) seeded.push({ role: "user", text: state.message });
    seeded.push({
      role: "bot",
      text: state.response ?? FALLBACK_RESPONSE,
      helpOfferType: state.helpOfferType,
      suggestionEntryKey: state.suggestionEntryKey,
    });
    return seeded;
  });
  const [draft, setDraft] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFailedText, setLastFailedText] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  // Rehydrates from what the backend actually persisted — the router state
  // Home hands off only ever seeds the FIRST exchange, and every turn added
  // after that lived purely in this component's state, gone on any refresh
  // or direct load. GET /conversation is the same source of truth Generate
  // itself reads from, so a refresh now shows the real thread instead of
  // silently losing everything past turn one. Preserves the just-delivered
  // helpOfferType (not stored server-side) by matching the fetched last
  // turn's text against what Home/ThinkingTrap just handed off — a stale
  // match after a real refresh just means the quiet line doesn't
  // resurface, which is fine, it's a live-session affordance, not a
  // permanent record.
  useEffect(() => {
    let cancelled = false;
    getConversation()
      .then((fetched) => {
        if (cancelled || fetched.length === 0) return;
        const mapped: Turn[] = fetched.map((t) => ({
          role: t.role === "user" ? "user" : "bot",
          text: t.content,
        }));
        const last = mapped[mapped.length - 1];
        if (last?.role === "bot" && last.text === state.response && state.helpOfferType) {
          last.helpOfferType = state.helpOfferType;
          last.suggestionEntryKey = state.suggestionEntryKey;
        }
        setTurns(mapped);
      })
      .catch(() => {
        // Non-critical background hydration — keep whatever's already
        // rendered (router-state seed or the fallback line) rather than
        // surfacing an error banner for this.
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function send(text: string) {
    setIsSubmitting(true);
    setError(null);
    setLastFailedText(null);
    try {
      const result = await sendMessage(text);
      if (result.crisis) {
        navigate("/crisis", { state: { helplines: result.helplines } });
        return;
      }
      setTurns((prev) => [
        ...prev,
        {
          role: "bot",
          text: result.response,
          helpOfferType: result.help_offer_type,
          suggestionEntryKey: result.suggestion_entry_key,
        },
      ]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong — mind trying again?");
      setLastFailedText(text);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleSend() {
    const text = draft.trim();
    if (!text || isSubmitting) return;
    setDraft("");
    setTurns((prev) => [...prev, { role: "user", text }]);
    void send(text);
  }

  function handleRetry() {
    if (!lastFailedText) return;
    void send(lastFailedText);
  }

  return (
    <div className="flex h-svh flex-col bg-background">
      <AppHeader back />

      <main className="flex min-h-0 flex-1 flex-col overflow-hidden px-edge-mobile pb-stack-md">
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto py-2">
          {turns.map((turn, i) => (
            <div key={i} className="flex flex-col gap-1.5">
              <ChatBubble variant={turn.role === "user" ? "user" : "companion"}>{turn.text}</ChatBubble>
              {turn.helpOfferType === "notice_thinking_trap" && (
                <button
                  type="button"
                  onClick={() => navigate("/thinking-trap")}
                  className="self-start pl-1 text-xs text-muted-foreground/70 underline"
                >
                  {QUIET_LINE_TEXT}
                </button>
              )}
              {turn.helpOfferType === "offer_suggestion" && turn.suggestionEntryKey?.startsWith("bt-") && (
                <button
                  type="button"
                  onClick={() => navigate("/breathe")}
                  className="self-start pl-1 text-xs text-muted-foreground/70 underline"
                >
                  {BREATHE_LINE_TEXT}
                </button>
              )}
            </div>
          ))}
          {isSubmitting && (
            <ChatBubble variant="companion">
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
            </ChatBubble>
          )}
          <div ref={endRef} />
        </div>

        {error && (
          <div className="mb-2 flex items-center justify-between gap-3 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <span>{error}</span>
            <button type="button" onClick={handleRetry} className="shrink-0 font-medium underline">
              Retry
            </button>
          </div>
        )}

        <div className="claymorphic-card flex flex-col gap-3 p-4">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Keep talking, if you want to…"
            disabled={isSubmitting}
            className="min-h-16 resize-none border-none bg-transparent p-0 text-base shadow-none focus-visible:ring-0"
          />
          <div className="flex items-center justify-between">
            <Mic className="size-5 text-muted-foreground" aria-hidden />
            <Button
              size="lg"
              className="rounded-full px-6"
              disabled={isSubmitting || draft.trim().length === 0}
              onClick={handleSend}
            >
              {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : "Send"}
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
