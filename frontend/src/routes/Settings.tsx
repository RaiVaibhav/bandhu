import { useState } from "react";
import { useNavigate } from "react-router";
import { Loader2 } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, deleteSession } from "@/lib/apiClient";
import { cn } from "@/lib/utils";

const LANGUAGE_STORAGE_KEY = "bandhu_language_preference";

/** ux-flow.html: "Language toggle, delete my data... Plain language, not
 * buried in a menu tree." Both are real actions, not decoration — but see
 * each section's own note for what's genuinely wired vs. not. */
export default function Settings() {
  const navigate = useNavigate();
  const [language, setLanguage] = useState<"en" | "hi">(
    () => (localStorage.getItem(LANGUAGE_STORAGE_KEY) as "en" | "hi") ?? "en",
  );
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function selectLanguage(next: "en" | "hi") {
    setLanguage(next);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, next);
  }

  async function handleDelete() {
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      return;
    }
    setIsDeleting(true);
    setError(null);
    try {
      await deleteSession();
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete your data — mind trying again?");
      setIsDeleting(false);
      setConfirmingDelete(false);
    }
  }

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <AppHeader back />

      <main className="flex flex-1 flex-col gap-stack-lg px-edge-mobile pb-stack-lg">
        <h1 className="font-heading text-xl font-semibold text-foreground">Settings</h1>

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-foreground">Language</h2>
          <div className="flex gap-2">
            {(["en", "hi"] as const).map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => selectLanguage(code)}
                className={cn(
                  "rounded-full px-4 py-2 text-sm",
                  language === code ? "bg-primary text-primary-foreground" : "bg-muted/60 text-muted-foreground",
                )}
              >
                {code === "en" ? "English" : "हिन्दी"}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground/70">
            Saved on this device only — Bandhu's replies aren't translated yet, this just remembers your preference
            for when they are.
          </p>
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-foreground">Privacy</h2>
          <Button variant="secondary" className="w-fit rounded-full" asChild>
            <a href="/privacy/">Privacy Policy</a>
          </Button>
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-foreground">Your data</h2>
          <Card className="border-l-4 border-l-destructive/60 py-4">
            <CardContent className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground leading-relaxed">
                This deletes everything Bandhu has stored about your check-ins — conversations, moods, and the
                rolling summary. It can't be undone.
              </p>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button
                variant="destructive"
                className="w-fit rounded-full"
                disabled={isDeleting}
                onClick={handleDelete}
              >
                {isDeleting ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : confirmingDelete ? (
                  "Tap again to confirm"
                ) : (
                  "Delete my data"
                )}
              </Button>
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}
