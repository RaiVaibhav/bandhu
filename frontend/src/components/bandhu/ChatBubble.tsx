import { cn } from "@/lib/utils";

type ChatBubbleProps = {
  children: React.ReactNode;
  variant?: "companion" | "user";
};

/** Response is a real back-and-forth thread (docs/ux-flow.html: "a real
 * companion conversation") — companion bubbles tail bottom-left, the
 * person's own messages tail bottom-right and sit on the right side. */
export function ChatBubble({ children, variant = "companion" }: ChatBubbleProps) {
  const isUser = variant === "user";
  return (
    <div
      className={cn(
        "max-w-[85%] rounded-2xl px-4 py-3 text-base leading-relaxed shadow-sm",
        isUser
          ? "bubble-user self-end bg-primary text-primary-foreground"
          : "bubble-companion self-start bg-card text-foreground ring-1 ring-foreground/5",
      )}
    >
      {children}
    </div>
  );
}
