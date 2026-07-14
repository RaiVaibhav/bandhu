// Real wiring to the FastAPI backend (backend/app/main.py's POST /message).
// Replaces the earlier mockPipeline.ts stand-in now that the two are
// actually connected — see frontend/README.md for the CORS/cookie setup
// this depends on (backend/app/main.py's CORSMiddleware, and the
// bandhu_sid cookie's `secure` flag being derived from the request scheme
// so it survives plain-http local dev).

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type Helpline = {
  org_name: string;
  phone_number: string;
  hours: string | null;
};

export type MessageApiResponse = {
  response: string;
  crisis: boolean;
  helplines: Helpline[];
  help_offer_type: string | null;
  suggestion_entry_key: string | null;
};

export type CheckinSummary = {
  date: string;
  mood_tag: string | null;
  theme: string | null;
};

export type LookingBackResponse = {
  summary_text: string | null;
  checkins: CheckinSummary[];
};

export type ConversationTurn = {
  role: string;
  content: string;
};

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Calls the real 12-stage pipeline (backend/app/pipeline/orchestrator.py)
 * for one check-in. `credentials: "include"` is required — the anonymous
 * session cookie (bandhu_sid) is how the backend recognizes returning
 * visitors and reads/writes conversation memory; without it, every call
 * would look like a brand-new session.
 */
export async function sendMessage(text: string): Promise<MessageApiResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/message`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } catch {
    throw new ApiError("Couldn't reach Bandhu's backend — check your connection.");
  }

  if (res.status === 429) {
    throw new ApiError("Too many check-ins too quickly — give it a moment.", 429);
  }
  if (!res.ok) {
    throw new ApiError(`Bandhu's backend had trouble with that (${res.status}).`, res.status);
  }

  return res.json();
}

/** Logs a direct "Breathe" tap — no message, no LLM call, see
 * backend/app/main.py's post_breathe. */
export async function postBreathe(): Promise<{ intro_text: string }> {
  const res = await fetch(`${API_BASE_URL}/breathe`, { method: "POST", credentials: "include" });
  if (!res.ok) {
    throw new ApiError(`Couldn't start that (${res.status}).`, res.status);
  }
  return res.json();
}

/** Backs the Looking Back screen — the Summarizer's rolling narrative plus
 * the raw per-check-in timeline, see backend/app/main.py's get_looking_back. */
export async function getLookingBack(): Promise<LookingBackResponse> {
  const res = await fetch(`${API_BASE_URL}/looking-back`, { credentials: "include" });
  if (!res.ok) {
    throw new ApiError(`Couldn't load that (${res.status}).`, res.status);
  }
  return res.json();
}

/** Settings' "delete my data" — cascades server-side, see
 * backend/app/main.py's delete_session. */
export async function deleteSession(): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/session`, { method: "DELETE", credentials: "include" });
  if (!res.ok) {
    throw new ApiError(`Couldn't delete that (${res.status}).`, res.status);
  }
}

/** Rehydrates Response.tsx's thread on load — see
 * backend/app/main.py's get_conversation. Same windowed recent-turns query
 * Generate itself reads from, not a full unbounded history. */
export async function getConversation(): Promise<ConversationTurn[]> {
  const res = await fetch(`${API_BASE_URL}/conversation`, { credentials: "include" });
  if (!res.ok) {
    throw new ApiError(`Couldn't load your conversation (${res.status}).`, res.status);
  }
  const data = await res.json();
  return data.turns;
}

/** The real Thinking Trap re-entry — bypasses Classify/Eligibility/
 * Orchestrator entirely (backend/app/main.py's post_thinking_trap) since
 * the person already named their own pattern; this isn't a fresh
 * discretionary judgment call, it's a deterministic, deeper follow-through
 * using that exact pattern's real content. */
export async function sendThinkingTrapSelection(patternKey: string): Promise<{ response: string }> {
  const res = await fetch(`${API_BASE_URL}/thinking-trap`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pattern_key: patternKey }),
  });
  if (!res.ok) {
    throw new ApiError(`Couldn't reach Bandhu's backend — check your connection.`, res.status);
  }
  return res.json();
}
