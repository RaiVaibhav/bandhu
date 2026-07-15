import { useLocation } from "react-router";
import { Phone } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { Helpline } from "@/lib/apiClient";

// Fallback only — used for the dev-only design preview (Home's "View
// Crisis Support" link) when there's no real backend response to show.
// Real, dial-confirmed numbers — see knowledge-base/safety/
// helpline-directory.md (verified 2026-07-13). Deliberately no WhatsApp
// link: the directory only confirms these connect by voice call, not that
// a WhatsApp number exists for them.
const FALLBACK_HELPLINES: Helpline[] = [
  { org_name: "Vandrevala Foundation", phone_number: "1860-266-2345", hours: null },
  { org_name: "Vandrevala Foundation", phone_number: "1800-233-3330", hours: null },
  { org_name: "iCall (TISS)", phone_number: "9152987821", hours: null },
  { org_name: "KIRAN", phone_number: "1800-599-0019", hours: null },
];

const ORG_DESCRIPTIONS: Record<string, string> = {
  "Vandrevala Foundation": "24x7 mental health helpline, multi-lingual support.",
  "iCall (TISS)": "Free telephone counseling by trained professionals.",
  KIRAN: "Government of India mental health helpline.",
};

function telHref(phoneNumber: string) {
  return `tel:${phoneNumber.replace(/[^0-9+]/g, "")}`;
}

function groupByOrg(helplines: Helpline[]) {
  const byOrg = new Map<string, Helpline[]>();
  for (const h of helplines) {
    const existing = byOrg.get(h.org_name);
    if (existing) existing.push(h);
    else byOrg.set(h.org_name, [h]);
  }
  return [...byOrg.entries()];
}

type CrisisSupportState = {
  helplines?: Helpline[];
};

/** Deliberately different in tone from every other screen — amber, not
 * alarm-red, per docs/ux-flow.html. Real numbers, zero cleverness: this is
 * a hand-off to a real person, not something the app manages further.
 * Prefers the live list the backend just returned (build_crisis_response,
 * app/pipeline/stages/crisis_response.py — only ever verified rows) over
 * the hardcoded fallback, so a real crisis card reflects the database of
 * record, not a frontend copy that could drift out of date. */
export default function CrisisSupport() {
  const location = useLocation();
  const state = (location.state ?? {}) as CrisisSupportState;
  const helplines = state.helplines && state.helplines.length > 0 ? state.helplines : FALLBACK_HELPLINES;

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <AppHeader back="/" />

      <main className="flex flex-1 flex-col gap-stack-md px-edge-mobile pb-stack-lg">
        <div className="flex flex-col gap-2">
          <h1 className="font-heading text-xl font-semibold text-foreground">
            You don't have to carry this alone
          </h1>
          <p className="text-sm text-muted-foreground leading-relaxed">
            These are free, and someone will actually pick up.
          </p>
        </div>

        <div className="flex flex-col gap-3">
          {groupByOrg(helplines).map(([org, numbers]) => (
            <Card key={org} className="border-l-4 py-4" style={{ borderLeftColor: "var(--color-status-safety)" }}>
              <CardContent className="flex flex-col gap-3">
                <div>
                  <p className="font-medium text-foreground">{org}</p>
                  {ORG_DESCRIPTIONS[org] && (
                    <p className="text-xs text-muted-foreground">{ORG_DESCRIPTIONS[org]}</p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {numbers.map((n) => (
                    <Button key={n.phone_number} asChild variant="secondary" className="rounded-full">
                      <a href={telHref(n.phone_number)}>
                        <Phone className="size-3.5" data-icon="inline-start" />
                        {n.phone_number}
                      </a>
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}

          <Card className="border-l-4 py-4" style={{ borderLeftColor: "var(--color-status-safety)" }}>
            <CardContent className="flex flex-col gap-3">
              <div>
                <p className="font-medium text-foreground">Medical Emergency</p>
                <p className="text-xs text-muted-foreground">National emergency number.</p>
              </div>
              <Button asChild className="w-fit rounded-full">
                <a href="tel:112">
                  <Phone className="size-3.5" data-icon="inline-start" />
                  Dial 112
                </a>
              </Button>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
