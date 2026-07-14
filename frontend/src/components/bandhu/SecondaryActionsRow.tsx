import { Wind, PenLine, Music, Feather } from "lucide-react";

const ACTIONS = [
  { icon: Wind, label: "Breathe" },
  { icon: PenLine, label: "Write Together" },
  { icon: Music, label: "Listen" },
  { icon: Feather, label: "Poem" },
];

/** Small and secondary, deliberately — see docs/ux-flow.html: these exist
 * but must never compete with the check-in input before the person has
 * said anything. Presentational only in this pass: Breathe, Co-Create, and
 * Listen are their own screens/features not built yet (see
 * backend-architecture.md §12/§13), so these are inert for now rather than
 * linking somewhere that doesn't exist. */
export function SecondaryActionsRow() {
  return (
    <div className="flex justify-center gap-5 opacity-70">
      {ACTIONS.map(({ icon: Icon, label }) => (
        <div key={label} className="flex flex-col items-center gap-1 text-muted-foreground">
          <div className="flex size-9 items-center justify-center rounded-full bg-muted/60">
            <Icon className="size-4" />
          </div>
          <span className="text-[10.5px]">{label}</span>
        </div>
      ))}
    </div>
  );
}
