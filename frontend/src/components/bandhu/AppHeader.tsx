import { useNavigate } from "react-router";
import { ChevronLeft, History, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";

/** `menu` shows Looking Back / Settings — the two screens ux-flow.html
 * describes as "always reachable, not part of the check-in sequence...
 * sit behind the bottom nav / menu." There's no bottom nav built yet, so
 * these two icon buttons on Home are the actual persistent entry point for
 * now, not a placeholder — see frontend/README.md.
 *
 * `back` takes the actual destination route, not a bare boolean — it used
 * to call `navigate(-1)` (raw browser history), which breaks the moment
 * this screen isn't reached the way the code assumes: a direct link, a
 * refresh that resets the SPA's in-memory history stack, or a route
 * reached via the client-side pushState navigation this app's own routes
 * use internally can all leave nothing meaningful to go "back" to, popping
 * the person somewhere unrelated (or out of the app) instead of to the
 * screen that actually, logically precedes this one. */
export function AppHeader({ back, menu }: { back?: string; menu?: boolean }) {
  const navigate = useNavigate();

  return (
    <header className="flex items-center h-14 px-edge-mobile shrink-0">
      {back ? (
        <Button
          variant="ghost"
          size="icon"
          aria-label="Back"
          onClick={() => navigate(back)}
          className="-ml-2"
        >
          <ChevronLeft className="size-5" />
        </Button>
      ) : (
        <div className="size-8" aria-hidden />
      )}
      <span className="flex-1 text-center font-heading text-base font-semibold text-foreground">
        Bandhu
      </span>
      {menu ? (
        <div className="-mr-2 flex items-center gap-1">
          <Button variant="ghost" size="icon" aria-label="Looking Back" onClick={() => navigate("/looking-back")}>
            <History className="size-4.5" />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Settings" onClick={() => navigate("/settings")}>
            <Settings className="size-4.5" />
          </Button>
        </div>
      ) : (
        <div className="size-8" aria-hidden />
      )}
    </header>
  );
}
