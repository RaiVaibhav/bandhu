import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { ApiError, getLookingBack, type LookingBackResponse } from "@/lib/apiClient";

const COLD_START_TEXT = "Nothing to look back on yet — check in a few times and a picture will start to form here.";

function groupByDate(checkins: LookingBackResponse["checkins"]) {
  const byDate = new Map<string, LookingBackResponse["checkins"]>();
  for (const c of checkins) {
    const existing = byDate.get(c.date);
    if (existing) existing.push(c);
    else byDate.set(c.date, [c]);
  }
  return [...byDate.entries()];
}

/** ux-flow.html: "Opens with one line summarizing the week... then the
 * daily timeline underneath as supporting detail, not the other way
 * around. No charts, no streaks." summary_text is the Summarizer's (stage
 * 11) rolling narrative — nightly batch job, so a brand-new session
 * genuinely has nothing here yet; that's a real cold start, not a loading
 * bug. */
export default function LookingBack() {
  const [data, setData] = useState<LookingBackResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLookingBack()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Couldn't load this right now.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <AppHeader back />

      <main className="flex flex-1 flex-col gap-stack-md px-edge-mobile pb-stack-lg">
        <h1 className="font-heading text-xl font-semibold text-foreground">Looking Back</h1>

        {isLoading && (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {data && (
          <>
            <p className="text-base leading-relaxed text-foreground">{data.summary_text ?? COLD_START_TEXT}</p>

            {data.checkins.length > 0 && (
              <div className="flex flex-col gap-3">
                {groupByDate(data.checkins).map(([date, entries]) => (
                  <div key={date} className="flex flex-col gap-1 border-l-2 border-muted pl-3">
                    <p className="text-xs font-medium text-muted-foreground">{date}</p>
                    {entries.map((e, i) => (
                      <p key={i} className="text-sm text-foreground">
                        {[e.mood_tag, e.theme].filter(Boolean).join(" · ") || "Checked in"}
                      </p>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
