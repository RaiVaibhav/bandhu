import { Phone } from "lucide-react";
import { AppHeader } from "@/components/bandhu/AppHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

// Real, dial-confirmed numbers only — see knowledge-base/safety/
// helpline-directory.md (verified 2026-07-13). Deliberately no WhatsApp
// link here: the directory only confirms these numbers connect by voice
// call, not that a WhatsApp number exists for them — inventing one would
// be exactly the failure mode that file warns against.
const HELPLINES = [
  {
    org: "Vandrevala Foundation",
    description: "24x7 mental health helpline, multi-lingual support.",
    numbers: [
      { label: "1860-266-2345", tel: "18602662345" },
      { label: "1800-233-3330", tel: "18002333330" },
    ],
  },
  {
    org: "iCall (TISS)",
    description: "Free telephone counseling by trained professionals.",
    numbers: [{ label: "9152987821", tel: "9152987821" }],
  },
  {
    org: "KIRAN",
    description: "Government of India mental health helpline.",
    numbers: [{ label: "1800-599-0019", tel: "18005990019" }],
  },
];

/** Deliberately different in tone from every other screen — amber, not
 * alarm-red, per docs/ux-flow.html. Real numbers, zero cleverness: this is
 * a hand-off to a real person, not something the app manages further. */
export default function CrisisSupport() {
  return (
    <div className="flex min-h-svh flex-col bg-background">
      <AppHeader back />

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
          {HELPLINES.map((h) => (
            <Card
              key={h.org}
              className="border-l-4 py-4"
              style={{ borderLeftColor: "var(--color-status-safety)" }}
            >
              <CardContent className="flex flex-col gap-3">
                <div>
                  <p className="font-medium text-foreground">{h.org}</p>
                  <p className="text-xs text-muted-foreground">{h.description}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {h.numbers.map((n) => (
                    <Button key={n.tel} asChild variant="secondary" className="rounded-full">
                      <a href={`tel:${n.tel}`}>
                        <Phone className="size-3.5" data-icon="inline-start" />
                        {n.label}
                      </a>
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}

          <Card
            className="border-l-4 py-4"
            style={{ borderLeftColor: "var(--color-status-safety)" }}
          >
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
