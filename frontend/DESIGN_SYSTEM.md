# Design system — extracted from Stitch, not guessed

Bandhu's Stitch project (`projects/1054452762569491480`, "Animated Hindi Companion") generates real standalone HTML mockups per screen, each with an inline `tailwind.config` and a Material-3-style CSS variable palette. Every token in `src/index.css` was read directly out of that generated HTML — `welcome.html`, `home.html`, `response.html`, `crisis.html` — not approximated from a screenshot.

## Where each piece came from

| Token group | Source | Notes |
|---|---|---|
| Core palette (`--primary`, `--background`, `--secondary`, etc.) | Stitch's own Material-3-style token set, same across all 4 mockups | No literal "terracotta"/"sage-green" keys exist in the source — `--primary` (`#42655b`) is the deep teal/sage-green tone; `--warm-sand` (`#f9f6f1`) is the closest to a terracotta-family background. |
| `--status-safety` (`#d97706`) | Stitch's own token name, used for Crisis Support's accent | Kept as its own semantic token rather than folded into `--destructive` — Crisis Support is deliberately amber, not alarm-red (docs/ux-flow.html). |
| Font — `Be Vietnam Pro` | `<style>` + Google Fonts `<link>` in every mockup | Loaded via `<link>` in both HTML entry points, not `@fontsource`, matching what Stitch itself does. |
| Claymorphic shadow recipe (`.claymorphic-card`) | `response.html`'s `.claymorphic-card` class, copied verbatim | The one hand-written CSS block outside Stitch's token system — a multi-layer composite shadow, not expressible as a single Tailwind shadow token, so it's kept as a utility class in `index.css`. |
| Chat bubble tail (`.bubble-companion`) | `response.html`, `border-bottom-left-radius: 4px` | Same reasoning — a one-off shape override, not a token. |
| Spacing scale (`stack-sm`, `gutter`, `stack-md`, `edge-mobile`, `edge-desktop`, `stack-lg`) | Identical custom `spacing` block in all 4 mockups' `tailwind.config` | Ported as Tailwind v4 `@theme` spacing tokens so components keep the exact rhythm they were designed with. |
| `pebble` border radius (`40% 60% 70% 30% / 40% 50% 60% 50%`) | `welcome.html`, used on its play/action button | Organic blob shape — available as `rounded-pebble`. |

## What did NOT get ported

- Stitch's `sidebar-*` and `chart-*` tokens (added by shadcn's `nova` preset default, not Stitch) — removed, this app has no dashboard/sidebar/chart surface.
- `Geist` font (shadcn's preset default) — replaced with `Be Vietnam Pro`, the font Stitch's own mockups actually use.
- The literal two-button decision card on `response.html` and the four prominent buttons on `home.html` ("Home (Evolved)") — both are visual mockups only; the actual interaction was built to `docs/ux-flow.html`'s corrected spec instead (single muted line; input stays dominant). See that doc's "Where this doesn't match the current Stitch build yet" section — these were already known, documented gaps between the Stitch prototype and the intended product, not something this frontend pass introduced.

## Mascot images

`public/mascot/` has two downloaded Stitch mascot renders:
- `mascot-cloud.jpg` — sitting upright, eyes open, alert/curious — used on **Welcome** and **Home**. This is the "meeting/greeting" pose.
- `mascot-meditative.jpg` — eyes closed, lotus position, mid-breath — **not used anywhere yet**. Reserved for the future Immersive Breathing screen (`docs/ux-flow.html`'s Breathing branch, not built in this pass) — it was originally (wrongly) used on Welcome, since an eyes-closed meditating pose reads as a breathing-exercise image, not a first-open greeting.

## Component layer

`src/components/ui/` is shadcn/ui (Radix primitives + Tailwind, `nova` preset, re-themed with the tokens above). `src/components/bandhu/` is bespoke — the pieces custom enough (mascot imagery, chat bubble, mood-tap row) that a generic component library doesn't model them.

## Re-extracting from Stitch later

`mcp__stitch__list_screens` (projectId `1054452762569491480`) lists every screen; each entry's `htmlCode.downloadUrl` is a live-fetchable, complete standalone HTML document. Several screens exist in more than one iteration (e.g. "Home" / "Home (Evolved)" / "Home Experience (Reimagined)") — check `docs/ux-flow.html`'s "known mismatch" notes before treating a later-named iteration as more correct; iteration order in Stitch isn't the same thing as UX-correctness.
