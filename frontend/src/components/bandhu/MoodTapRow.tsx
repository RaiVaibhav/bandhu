import { cn } from "@/lib/utils";

export type Mood = "low" | "okay" | "good" | "anxious";

const MOODS: { value: Mood; emoji: string; label: string }[] = [
  { value: "low", emoji: "😔", label: "Low" },
  { value: "anxious", emoji: "😣", label: "Anxious" },
  { value: "okay", emoji: "😐", label: "Okay" },
  { value: "good", emoji: "🙂", label: "Good" },
];

/** Secondary, not the point of the screen — see docs/ux-flow.html: "The
 * text input is the one dominant thing on screen." This row sits small and
 * quiet above it, matching pipeline.html's ingest stress case where a
 * mood-tap alone (no text) is itself a valid check-in. */
export function MoodTapRow({
  value,
  onChange,
}: {
  value: Mood | null;
  onChange: (mood: Mood) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-medium text-muted-foreground">How is your energy?</span>
      <div className="flex gap-2">
        {MOODS.map((mood) => (
          <button
            key={mood.value}
            type="button"
            onClick={() => onChange(mood.value)}
            aria-pressed={value === mood.value}
            className={cn(
              "flex flex-col items-center gap-1 rounded-xl px-3 py-2 text-xs text-muted-foreground transition-colors",
              value === mood.value
                ? "bg-accent text-accent-foreground ring-1 ring-primary/30"
                : "bg-muted/60 hover:bg-muted",
            )}
          >
            <span className="text-lg leading-none">{mood.emoji}</span>
            {mood.label}
          </button>
        ))}
      </div>
    </div>
  );
}
