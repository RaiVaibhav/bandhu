import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { Loader2 } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { ChatBubble } from "@/components/bandhu/ChatBubble";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, getConversation, streamMessage, type Helpline } from "@/lib/apiClient";

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
  // Home now hands off only the raw text, before any backend call — this
  // route fires the actual streamed request itself (see the mount effect
  // below), which is what lets the very first exchange stream in too,
  // instead of Home blocking on a full round-trip before this screen even
  // appears. ThinkingTrap still hands off a fully-resolved {message,
  // response} pair (its own POST /thinking-trap isn't streamed), so that
  // case is seeded as already-complete and never re-sent here.
  const isFreshSend = Boolean(state.message) && !state.response;

  const [turns, setTurns] = useState<Turn[]>(() => {
    if (!state.message && !state.response) return [{ role: "bot", text: FALLBACK_RESPONSE }];
    const seeded: Turn[] = [];
    if (state.message) seeded.push({ role: "user", text: state.message });
    if (state.response) {
      seeded.push({
        role: "bot",
        text: state.response,
        helpOfferType: state.helpOfferType,
        suggestionEntryKey: state.suggestionEntryKey,
      });
    }
    return seeded;
  });
  // Text of the in-progress companion reply, growing as delta events
  // arrive — null when nothing is streaming right now. Empty string (not
  // null) while waiting on the first delta, so the loading spinner and the
  // growing text are really the same bubble, not a swap between two.
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFailedText, setLastFailedText] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const hasSentInitialRef = useRef(false);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns, streamingText]);

  // Rehydrates from what the backend actually persisted — but ONLY for a
  // genuine direct load (no router state at all, e.g. a refresh), which is
  // the one case with nothing already known to show. Both hand-off shapes
  // already carry everything this screen needs locally: a fresh send from
  // Home (isFreshSend) hasn't been persisted server-side yet at mount time,
  // so rehydrating here would race the in-flight stream and overwrite the
  // optimistic user bubble with older history that doesn't include it yet;
  // and ThinkingTrap's already-resolved {message, response} pair is, per
  // its own hand-off contract, already complete — re-fetching here pulls in
  // this session's ENTIRE prior history underneath it instead of just the
  // one exchange that was just completed, which reads as old messages
  // suddenly reappearing rather than a continuing conversation. Bounded to
  // "no state.message at all" rather than isFreshSend alone.
  useEffect(() => {
    if (state.message) return;
    let cancelled = false;
    getConversation()
      .then((fetched) => {
        if (cancelled || fetched.length === 0) return;
        const mapped: Turn[] = fetched.map((t) => ({
          role: t.role === "user" ? "user" : "bot",
          text: t.content,
        }));
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
    setStreamingText("");
    try {
      let receivedDone = false;
      let finalResponse = "";
      let finalCrisis = false;
      let finalHelplines: Helpline[] = [];
      let finalHelpOfferType: string | null = null;
      let finalSuggestionEntryKey: string | null = null;

      await streamMessage(text, (event) => {
        if (event.type === "delta") {
          setStreamingText((prev) => (prev ?? "") + event.text);
        } else if (event.type === "reset") {
          setStreamingText("");
        } else if (event.type === "done") {
          receivedDone = true;
          finalResponse = event.response;
          finalCrisis = event.crisis;
          finalHelplines = event.helplines;
          finalHelpOfferType = event.help_offer_type;
          finalSuggestionEntryKey = event.suggestion_entry_key;
        }
      });

      // The connection closed before a "done" event arrived — whatever's
      // in streamingText is incomplete and shouldn't be treated as the
      // real reply.
      if (!receivedDone) throw new ApiError("Lost connection partway through — mind trying again?");

      if (finalCrisis) {
        navigate("/crisis", { state: { helplines: finalHelplines } });
        return;
      }
      setTurns((prev) => [
        ...prev,
        { role: "bot", text: finalResponse, helpOfferType: finalHelpOfferType, suggestionEntryKey: finalSuggestionEntryKey },
      ]);
      setStreamingText(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong — mind trying again?");
      setLastFailedText(text);
      setStreamingText(null);
    } finally {
      setIsSubmitting(false);
    }
  }

  // Fires the actual send for a fresh hand-off from Home — turns is already
  // seeded with the user's bubble above, so this only needs to produce the
  // reply. Guarded by a ref (not just the isFreshSend check) because
  // StrictMode double-invokes effects in dev; without the ref, that would
  // fire two real requests for the same message.
  useEffect(() => {
    if (isFreshSend && !hasSentInitialRef.current) {
      hasSentInitialRef.current = true;
      void send(state.message!);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      <AppHeader back="/" />

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
          {streamingText !== null && (
            <ChatBubble variant="companion">
              {streamingText.length > 0 ? (
                streamingText
              ) : (
                <span className="animate-text-shimmer font-medium">Listening…</span>
              )}
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
          <div className="flex items-center justify-end">
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
