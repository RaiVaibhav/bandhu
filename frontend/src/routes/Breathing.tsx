import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { X } from "lucide-react";
import { postBreathe } from "@/lib/apiClient";

const MASCOT_MEDITATIVE_URL = "/mascot/mascot-meditative.jpg";

// 4s in / 4s hold / 4s out — a generic, universally-taught pacing pattern,
// not sourced clinical content. knowledge-base/vetted/grounding-and-
// psychoeducation.md's own "What's deliberately not here" note: mhGAP
// explicitly excludes breathing/relaxation scripts, so there's no vetted
// entry this could be checked against — see backend/app/main.py's
// post_breathe for the same reasoning server-side. The glow/scale pulse
// itself is a single continuous 12s CSS animation (.animate-breathe-scale,
// index.css) — phases below only drive the text label and spoken cue, so
// the visual never abruptly jumps between discrete states the way a
// JS-toggled scale class used to (the "broken circle" this replaces).
const PHASES = [
  { label: "Breathe in…", seconds: 4, say: "Breathe in" },
  { label: "Hold", seconds: 4, say: "Hold" },
  { label: "Breathe out…", seconds: 4, say: "Breathe out" },
] as const;

/** Full screen, one-tap exit, "stay as long as you need" — see
 * docs/ux-flow.html. No completion required: the cycle just loops until
 * the person leaves. Visual treatment ported from Stitch's "Immersive
 * Breathing Experience" mockup (frontend/DESIGN_SYSTEM.md). */
export default function Breathing() {
  const navigate = useNavigate();
  const [phaseIndex, setPhaseIndex] = useState(0);

  useEffect(() => {
    void postBreathe();
  }, []);

  useEffect(() => {
    const phase = PHASES[phaseIndex];

    // Spoken cue — genuinely optional, feature-detected: not every browser
    // exposes speechSynthesis, and some require a prior user gesture
    // before allowing audio, which a page freshly navigated to may not
    // have had yet. Silently does nothing rather than throwing either way.
    if ("speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(phase.say);
        utterance.rate = 0.85;
        utterance.volume = 0.6;
        window.speechSynthesis.speak(utterance);
      } catch {
        // Non-critical — the on-screen label still carries the same cue.
      }
    }

    const timer = setTimeout(() => {
      setPhaseIndex((i) => (i + 1) % PHASES.length);
    }, phase.seconds * 1000);
    return () => clearTimeout(timer);
  }, [phaseIndex]);

  useEffect(() => {
    return () => {
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    };
  }, []);

  const phase = PHASES[phaseIndex];

  return (
    <div className="breathing-bg relative flex min-h-svh flex-col items-center justify-center overflow-hidden px-edge-mobile">
      <button
        type="button"
        onClick={() => navigate(-1)}
        aria-label="Exit"
        className="absolute right-edge-mobile top-6 z-10 flex size-12 items-center justify-center rounded-full bg-white/30 text-primary backdrop-blur-sm transition-colors hover:bg-white/50"
      >
        <X className="size-6 font-light" />
      </button>

      <div className="relative z-0 flex h-16 items-center justify-center">
        <p key={phaseIndex} className="animate-in fade-in font-heading text-2xl font-medium text-primary duration-700">
          {phase.label}
        </p>
      </div>

      <div className="relative mt-stack-lg flex h-64 w-64 items-center justify-center md:h-80 md:w-80">
        <div className="animate-breathe-scale absolute inset-0 rounded-full bg-secondary/40 opacity-60 blur-[80px]" />
        <img
          src={MASCOT_MEDITATIVE_URL}
          alt=""
          className="animate-breathe-scale relative z-10 h-full w-full rounded-full object-cover shadow-sm"
        />
      </div>

      <p className="mt-stack-lg text-xs text-muted-foreground/60">Stay as long as you need</p>
    </div>
  );
}
