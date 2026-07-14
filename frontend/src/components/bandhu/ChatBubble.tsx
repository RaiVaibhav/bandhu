import { cn } from "@/lib/utils";

/** The acknowledgment bubble on Response — see docs/ux-flow.html:
 * "Acknowledgment — always, and always complete alone." No tail-to-tail
 * chat thread here; this is deliberately the only bubble on screen. */
export function ChatBubble({ children }: { children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "bubble-companion max-w-[85%] rounded-2xl bg-card px-4 py-3 text-base leading-relaxed text-foreground shadow-sm ring-1 ring-foreground/5",
      )}
    >
      {children}
    </div>
  );
}
