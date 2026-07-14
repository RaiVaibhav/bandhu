import type { Mood } from "@/components/bandhu/MoodTapRow";

export type MockPipelineResult = {
  acknowledgment: string;
  helpOfferLine: string | null;
};

const ACKNOWLEDGMENTS: Record<Mood, string[]> = {
  low: ["I hear you. That sounds like a lot to carry.", "That sounds heavy — thank you for telling me."],
  anxious: ["That sounds like a lot to be holding right now.", "I hear how much is spinning right now."],
  okay: ["Thanks for checking in — good to know where you're at.", "Noted, gently. I'm here either way."],
  good: ["That's good to hear.", "Glad today has some room in it."],
};

const GENERIC_ACKNOWLEDGMENTS = [
  "I hear you. Thank you for sharing that.",
  "That sounds like a lot to carry.",
];

/**
 * Stand-in for the real backend pipeline (see backend/app/pipeline/
 * orchestrator.py) — this frontend pass is UI-only, no API wiring yet.
 * Picks a plausible acknowledgment and, for longer messages, a single
 * muted help-offer line — deliberately never a two-button decision, per
 * docs/ux-flow.html's corrected Response spec. Replace this whole module
 * with a real POST /message call once the backend is reachable from here.
 */
export function runMockPipeline(message: string, mood: Mood | null): MockPipelineResult {
  const pool = mood ? ACKNOWLEDGMENTS[mood] : GENERIC_ACKNOWLEDGMENTS;
  const acknowledgment = pool[message.length % pool.length];

  const eligible = message.trim().length > 20;
  const helpOfferLine = eligible ? "a 30-second grounding breath, if you want it" : null;

  return { acknowledgment, helpOfferLine };
}
