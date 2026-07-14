import { useNavigate } from "react-router";
import { ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

export function AppHeader({ back }: { back?: boolean }) {
  const navigate = useNavigate();

  return (
    <header className="flex items-center h-14 px-edge-mobile shrink-0">
      {back ? (
        <Button
          variant="ghost"
          size="icon"
          aria-label="Back"
          onClick={() => navigate(-1)}
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
      <div className="size-8" aria-hidden />
    </header>
  );
}
