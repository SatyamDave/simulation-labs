# simulation labs Design System — Comprehensive Specification

## v3 — Quiet workspace (Notion × Ollama), supersedes v2

> **Concept: a calm paper workspace, not an instrument panel.** The product
> watches synthetic users fail; the UI stays quiet about it. Personality comes
> from restraint and exactly one playful touch. Whitespace is the material.
> Everything in this v3 section **supersedes** v2 and v1 wherever they
> conflict; the older specs remain below as historical reference only.

### What v3 explicitly removes from v2

Bezel cards, corner tags, telemetry strip panels, scanlines, EKG heartbeat
traces, amber lamp fills, red 2px borders, tinted state panels (`bg-fail/10`
washes), the blinking caret, `>` console prefixes, grayscale death washes,
Archivo and the expanded display voice, uppercase tracked eyebrows, hover
scale/lift animations, and the bracketed `[simulation labs]` wordmark (now
plain lowercase `simulation labs`, mono, `text-sm`, everywhere).

### Color tokens (light-FIRST; `.dark` mechanism unchanged)

| Token | Light (primary) | Dark ("Notion-dark") |
|---|---|---|
| `--background` | `#FFFFFF` | `#191919` |
| `--surface` (subtle fill: tracks, image letterbox) | `#F7F7F5` | `#202020` |
| `--card` | `#FFFFFF` | `#202020` |
| `--border` (hairline — use sparingly) | `#E9E8E4` | `#2E2E2C` |
| `--foreground` | `#1D1D1B` | `#EDEDEB` |
| `--muted-foreground` (dim) | `#787774` | `#9B9B98` |
| `--hover` (faint tint) | `rgba(0,0,0,.035)` | `rgba(255,255,255,.055)` |
| `--primary` / `--primary-foreground` (solid button) | `#1D1D1B` / `#FFFFFF` | `#EDEDEB` / `#191919` |

**Functional colors are QUIET** — small dots, text, hairlines, thin bars only.
Never large fills, washes, tinted panels, or colored borders around content:

| State | Token | Light | Dark (lightened for contrast) |
|---|---|---|---|
| running / live | `--live` | `#D9730D` | `#DE8248` |
| survived | `--ok` | `#448361` | `#55A377` |
| died / abandoned | `--fail` | `#D44C47` | `#E0605A` |
| infra error | `--idle` | `#787774` | `#9B9B98` |

`theme.ts` keeps its export names; `OUTCOME_COLOR` points at these CSS vars.

### Typography

- **Inter (400/500/600) for everything.** Headlines are **semibold (600)**,
  tight (`tracking-tight`), compact — `text-4xl`/`text-5xl` max. Confident and
  friendly, never thin, never expanded. Body 400; names/labels 500.
- **IBM Plex Mono only for tiny data moments**: coordinates, step counts, the
  target URL, persona perturbation tags, telemetry tallies — always `text-xs`
  or smaller, always dim, always lowercase. No uppercase anywhere.
- Copy: sentence case, short, plain verbs (Notion voice).

### Shape, depth, motion

- Radius: `rounded-xl` (12px) cards, `rounded-lg` (8px) inputs/buttons/images.
  No pills except dots.
- Shadows: at most `0 1px 2px rgba(0,0,0,.05)`; mostly rely on hairlines +
  whitespace.
- Buttons: primary = solid `bg-primary text-primary-foreground rounded-lg
  font-medium` (near-black on light, inverted on dark). Secondary/ghost = no
  border, dim text, `hover:bg-hover` tint. No scale/lift animations — hover is
  a background tint or border darkening only.
- Motion: entrance fades are opacity-only, 0.2s, barely perceptible. Status
  dots may pulse opacity. `MotionConfig reducedMotion="user"` + the global
  reduced-motion kill-switch stay.

### The signature (the ONE playful element)

The vital line, shrunk to a whisper (`VitalLine.tsx`):

- A **1px sparkline, full width × 12px, at the very bottom of each tile** —
  a small dim-gray blip drifting left while running; flat dim-green on
  success; flat red with a tiny gap at the death point (`deathFrac`).
- The launch page's mark: **`FlatlineGlyph`** — a 120×24 inline-SVG hairline
  that blips once then flatlines, drawn in text color, above the headline.
  The whole product story in one glyph. No other decoration anywhere.

### Patterns

- **Header**: lowercase mono `simulation labs` wordmark (click = home) +
  theme toggle. Nothing else. Featherweight hairline underneath.
- **Launch**: centered single column `max-w-xl`. Glyph → semibold headline
  ("See where users give up.") → one dim sentence → URL command bar (mono,
  `rounded-lg`, hairline, subtle focus ring) with three tiny dim example
  links → task input → personas as quiet checkable chips (name + tiny mono
  tag; checked = near-black border + check, no color fills) → full-width
  solid "Run simulation" → "or watch the offline demo →" as a dim text link.
- **Live telemetry**: ONE quiet mono line — `• 2 survived · • 4 abandoned ·
  6/6 finished` with tiny colored dots; target URL right-aligned. No panels.
- **Tile**: hairline `rounded-xl` card → name (Inter 500) + tiny mono tags →
  full-color screenshot in a `rounded-lg` hairline frame → one dim caption
  line → outcome as dot + words (`died at step 4` in red, `survived · step 7`
  in green, mono `text-[11px]`) → whisper vital line pinned to the bottom.
- **Death treatment**: screenshot stays full color. A small red crosshair
  ring (1px ring + center dot) at `failure_coords`, coords in a tiny mono
  chip beside it (flips near the right edge), and the failure reason as one
  dim red line under the caption.
- **Report**: a Notion document — `max-w-3xl` centered. Big semibold
  completion % in the outcome color, headline sentence, then sections
  separated by generous space + hairlines (no cards unless needed): verdict
  as one line with a colored dot; survival bars 8px `rounded-full` in muted
  green/red on a `--surface` track with dim mono labels; heatmap image with
  rounded corners + hairline, soft radial marks topped by precise
  ring-and-dot markers; receipts as quiet hairline cards.

### Still in force

No emoji. No decorative color or gradients. Inline stroke SVG icons.
Contract/business logic untouched (`runReducer`, `useRunStream`, `api`,
`offline`, `types`). Both themes fully designed.

---

*The remainder of this document is the v2 and v1 specs, kept as historical
reference. Where they conflict with v3 above, v3 wins.*

---

## v2 — Instrument Panel (superseded by v3)

> **Concept: instrument panel, not landing page.** Simulation Labs is a lab
> bench where specimens (personas) run and flatline. The UI is a precision
> monitoring console, not SaaS marketing. Everything below in this v2 section
> **supersedes** the v1 spec wherever the two conflict; v1 remains as
> reference for anything v2 does not address.

### What v2 explicitly relaxes from v1

1. **System-fonts-only is repealed.** v2 loads two Google fonts (below).
   The v1 "no custom web fonts" anti-pattern no longer applies.
2. **The single-accent (emerald-only) rule is repealed.** v2 uses a
   four-value *functional state palette* — amber, emerald, red, neutral.
   These are states, not accents; the "no decorative color" principle stays
   absolute (a color may only appear when it encodes the state it names).
3. Pill-shaped (`rounded-full`) buttons/inputs are replaced by small-radius
   instrument controls (`--radius: 6px`; `rounded-md`/`rounded-lg`).
   `rounded-full` survives only for status lamp dots.
4. Ultra-light (300) display type is replaced by the display voice below.
5. Background blobs, shimmer borders, glass-blur header, and hover-lift on
   non-interactive cards are removed. Motion is entrances (once), `whileTap`,
   status-lamp pulses, and the vital line itself.

### Color tokens

Dark is the primary look ("graphite-blue void"); light is "lab paper". The
`.dark` class mechanism, theme toggle, and pre-paint script are unchanged.

| Token | Dark (default) | Light ("lab paper") |
|---|---|---|
| `--background` | `#0A0C0F` | `#F7F8FA` |
| `--panel` | `#11141A` | `#FFFFFF` |
| `--panel-raised` | `#171B23` | `#FDFDFE` |
| `--hairline` | `#1A1F29` | `#ECEFF3` |
| `--border` | `#232935` | `#E3E6EC` |
| `--foreground` (text) | `#E8EAF0` | `#14171C` |
| `--muted-foreground` (dim) | `#8B93A5` | `#5C6577` |

**Functional state palette — every color means something:**

| State | Token | Dark | Light (AA-darkened) | Meaning |
|---|---|---|---|---|
| RUNNING / live | `--live` (amber) | `#FFB224` | `#A36A00` | control-panel "active" lamp, live stream, armed roster lamps, launch button |
| SURVIVED | `--ok` (emerald) | `#2FD08C` | `#0E8F5B` | task completed |
| DIED / abandoned | `--fail` (red) | `#FF4D4D` | `#D92D2D` | genuine human abandon |
| infra error | `--idle` (neutral) | `#8B93A5` | `#5C6577` | excluded from survival stats |

Washes are made with `/10`–`/15` opacity of the state color (e.g.
`bg-fail/10`). **No other hues, ever.** Tailwind utilities: `text-live`,
`bg-ok`, `border-fail`, `text-idle`, `text-on-live` (text on an amber fill).
`theme.ts` exports `OUTCOME_COLOR` as CSS `var()` strings so charts stay AA
in both themes.

### Typography

Two Google fonts (loaded in `index.html`; keep the theme pre-paint script and
favicon beside the `<link>`s):

- **Archivo (variable: wght + wdth)** — display AND body.
  - Display voice (`.font-display`): weight **600**, `font-stretch: 118%`
    (semi-expanded — instrumentation signage), tight leading (`1.05`),
    `-0.015em` tracking, sentence case. Used for headlines and the big
    completion metric.
  - Body: 400, normal width. Persona names on cards: Archivo 500.
- **IBM Plex Mono** — ALL data, labels, eyebrows, coordinates, metrics,
  console lines, telemetry readings, buttons that arm/act. Eyebrows/labels
  are `text-[9px]`–`text-xs` uppercase `tracking-widest`. Numbers always
  `tabular-nums`.

### The signature: the vital-sign line (`VitalLine.tsx`)

A per-persona EKG strip (~24–28px tall, full tile width, pinned to the card
bottom) — the element the page is remembered by:

- **running** — repeating heartbeat pulse scrolling leftward in amber
  (CSS `translateX` loop of exactly one 120-unit cycle; 1.15s/cycle).
- **success** — settles into a calm, gentler pulse in emerald (2.8s/cycle).
- **abandoned** — FLATLINE: flat red line with a small break at the death
  step (`deathFrac = steps_survived / max_steps`), one collapsing blip before
  the break, dimmed dead-flat tail after it. Animation stops dead.
- **pending** — faint neutral baseline (standby).

Implementation: inline SVG. Live states use a fixed-scale viewBox with
`preserveAspectRatio="xMinYMid slice"` so the waveform never stretches;
flatline uses `preserveAspectRatio="none"` (a horizontal line is invariant
under stretch) + `vector-effect: non-scaling-stroke`. Reduced motion freezes
each state to a legible static frame. One aggregate vital line lives in the
run telemetry strip and under the report's completion metric.

### Instrument patterns

- **Telemetry strip** (live run header): ONE horizontal instrument bar, mono
  + `tabular-nums`: `SURVIVED 2 · ABANDONED 4 · RUNNING 2 · 6/8 FINISHED`
  with numbers in their state colors, the aggregate vital line, and
  task/target beneath in mono. Never metric cards.
- **Specimen card** (persona tile): identity row (status lamp + Archivo-500
  name + tiny mono perturbation labels) → bezel viewport → console lines →
  vital line.
- **Bezel viewport** (`.viewport-bezel`): screenshot in a thin-bordered,
  inset-shadowed frame on `bg-background` so letterboxing looks intentional;
  scanline overlay on top.
- **Console line**: mono `> …` line under the viewport; amber blinking caret
  while running (`.caret-blink`).
- **Death treatment**: never wash the tile red. Desaturate the final
  screenshot (`grayscale(0.8)`), 2px red viewport border, red corner tag
  `DIED · STEP 4`, calibration crosshair at `failure_coords` (full-width +
  full-height red hairlines + center ring) with the mono coord chip riding
  the top edge of the vertical hairline (flips side near the right edge; the
  epitaph lives *below* the viewport as a red console line, so they can never
  collide).
- **Success treatment**: emerald corner tag `SURVIVED · STEP 7`, 1px emerald
  viewport border, no desaturation.
- **Mission config** (launch): two-column console on `md+` — thesis left,
  launch panel right as a raised bezel card (`bg-panel-raised`, 1px border,
  mono corner label `MISSION CONFIG`). Roster entries are channel strips
  with amber "armed" lamps. The launch button is the one amber fill on the
  page (`bg-live text-on-live`, mono uppercase).
- **Header**: `[simulation labs]` mono wordmark, right-aligned mono status
  cluster (state lamp + `STANDBY / LIVE · STREAMING / REPLAY / REPORT`),
  hairline underneath, solid background (no glass blur).

### Still in force from v1

No emoji anywhere. Sentence-case copy, plain verbs. No decorative color or
gradients. Inline stroke SVG icons. `viewport={{ once: true }}` on all
in-view entrances. `MotionConfig reducedMotion="user"` plus the global
reduced-motion CSS kill-switch. Generous `px-6` section padding (containers
are now `max-w-6xl`).

---

*The remainder of this document is the original v1 spec, kept as reference.
Where it conflicts with v2 above, v2 wins.*

---

A precise, opinionated design specification extracted from the production [simulation labs] landing page. This document is the single source of truth for all visual decisions. When building UI for Simulation Labs, follow these patterns exactly — do not improvise or add generic "AI-generated" flourishes.

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Brand Identity](#brand-identity)
3. [Color System](#color-system)
4. [Typography](#typography)
5. [Spacing & Layout](#spacing--layout)
6. [Border, Radius & Shadows](#border-radius--shadows)
7. [Component Patterns](#component-patterns)
8. [Animation & Motion](#animation--motion)
9. [Background & Decorative Effects](#background--decorative-effects)
10. [Iconography](#iconography)
11. [Responsive Behavior](#responsive-behavior)
12. [Voice & Tone](#voice--tone)
13. [Anti-Patterns (What NOT to Do)](#anti-patterns)
14. [Complete Code Examples](#complete-code-examples)

---

## Design Philosophy

Simulation Labs' visual language is **infrastructure-grade minimal** — closer to Stripe, Linear, and Vercel than to colorful consumer SaaS. The aesthetic communicates trust, precision, and technical sophistication through restraint.

### Core Principles

1. **Monochrome-first**: The palette is almost entirely achromatic (black, white, grays). Color is used only for functional accents (emerald for success, red for errors). Never add decorative color.
2. **Typography-driven hierarchy**: Contrast between light (300) display text and medium (500) labels creates hierarchy. We do NOT rely on color, boxes, or visual noise.
3. **Generous negative space**: Sections use 128px (py-32) vertical padding. Let content breathe. More space = more premium.
4. **Subtle motion, not flashy animation**: Animations are slow, understated, and purposeful. No bouncing, no spinning, no attention-grabbing effects.
5. **System fonts only**: No custom font loading. We use the OS native font stack for both sans-serif and monospace.
6. **Dark mode is native**: Not an afterthought. Both modes are fully designed with proper contrast.

### What Makes Simulation Labs NOT Look Generic

- Ultra-light font weight (300) for all headlines — this is the #1 differentiator
- `[simulation labs]` bracket branding in monospace throughout
- CRT scanline effect on specific sections (retro-tech aesthetic)
- Shimmer button borders (rotating conic gradient)
- Animated background blobs that move very slowly (20-25 second cycles)
- Pill-shaped buttons (rounded-full) creating a soft, modern feel
- Eyebrow labels in monospace above every section
- Very subtle borders using transparency (border-border/40)
- Glass morphism header with backdrop-blur

---

## Brand Identity

### Logo

```
[simulation labs]
```

| Property | Value |
|----------|-------|
| Text | `[simulation labs]` — lowercase, with square brackets |
| Font | Monospace (`font-mono`) |
| Weight | Medium (500) — `font-medium` |
| Size | `text-lg` (1.125rem / 18px) in header |
| Hover | `hover:opacity-70 transition-opacity` |

**Tailwind class for logo:**
```
className="text-lg font-mono font-medium hover:opacity-70 transition-opacity"
```

The brackets represent structure and technical precision. Never remove them. Never use title case. Never add an icon/graphic alongside the wordmark.

---

## Color System

### Design Rule
The palette is **entirely achromatic** (zero chroma in oklch). All color tokens have `0 0` for chroma and hue. The only chromatic colors are functional accents (emerald, red).

### CSS Custom Properties (from index.css)

#### Light Mode (`:root`)
```css
:root {
  --radius: 0.625rem;
  --background: oklch(1 0 0);              /* #FFFFFF — pure white */
  --foreground: oklch(0.145 0 0);           /* #1A1A1A — near-black */
  --card: oklch(1 0 0);                     /* #FFFFFF */
  --card-foreground: oklch(0.145 0 0);      /* #1A1A1A */
  --popover: oklch(1 0 0);                  /* #FFFFFF */
  --popover-foreground: oklch(0.145 0 0);   /* #1A1A1A */
  --primary: oklch(0.205 0 0);              /* #2B2B2B — very dark gray */
  --primary-foreground: oklch(0.985 0 0);   /* #FAFAFA — off-white */
  --secondary: oklch(0.97 0 0);             /* #F5F5F5 — very light gray */
  --secondary-foreground: oklch(0.205 0 0); /* #2B2B2B */
  --muted: oklch(0.97 0 0);                 /* #F5F5F5 */
  --muted-foreground: oklch(0.556 0 0);     /* #737373 — mid gray */
  --accent: oklch(0.97 0 0);                /* #F5F5F5 */
  --accent-foreground: oklch(0.205 0 0);    /* #2B2B2B */
  --destructive: oklch(0.577 0.245 27.325); /* red */
  --border: oklch(0.922 0 0);               /* #E5E5E5 — light gray */
  --input: oklch(0.922 0 0);                /* #E5E5E5 */
  --ring: oklch(0.708 0 0);                 /* #A3A3A3 */
}
```

#### Dark Mode (`.dark`)
```css
.dark {
  --background: oklch(0.145 0 0);           /* #1A1A1A — near-black */
  --foreground: oklch(0.985 0 0);           /* #FAFAFA — off-white */
  --card: oklch(0.205 0 0);                 /* #2B2B2B — dark gray */
  --card-foreground: oklch(0.985 0 0);      /* #FAFAFA */
  --popover: oklch(0.205 0 0);              /* #2B2B2B */
  --popover-foreground: oklch(0.985 0 0);   /* #FAFAFA */
  --primary: oklch(0.922 0 0);              /* #E5E5E5 — light gray */
  --primary-foreground: oklch(0.205 0 0);   /* #2B2B2B */
  --secondary: oklch(0.269 0 0);            /* #3D3D3D */
  --secondary-foreground: oklch(0.985 0 0); /* #FAFAFA */
  --muted: oklch(0.269 0 0);                /* #3D3D3D */
  --muted-foreground: oklch(0.708 0 0);     /* #A3A3A3 */
  --accent: oklch(0.269 0 0);               /* #3D3D3D */
  --accent-foreground: oklch(0.985 0 0);    /* #FAFAFA */
  --destructive: oklch(0.704 0.191 22.216); /* lighter red */
  --border: oklch(1 0 0 / 10%);             /* white at 10% opacity */
  --input: oklch(1 0 0 / 15%);              /* white at 15% opacity */
  --ring: oklch(0.556 0 0);                 /* mid gray */
}
```

#### Functional Accent Colors (Used Sparingly)
| Color | Tailwind Class | Hex | Usage |
|-------|---------------|-----|-------|
| Emerald 500 | `text-emerald-500`, `bg-emerald-500` | `#10B981` | Live indicators, success states, positive check marks |
| Emerald 400 | `text-emerald-400` | `#34D399` | Savings badges |
| Red 500 | `text-red-500` | `#EF4444` | Error messages, destructive actions |

#### How Colors Are Applied
- **Primary text**: `text-foreground` (near-black in light, off-white in dark)
- **Secondary text**: `text-muted-foreground` (gray — used for descriptions, subtitles, metadata)
- **Highlighted text within muted sentences**: Use `<span className="text-foreground">` inside muted text
- **Backgrounds**: `bg-background` (page), `bg-muted/30` (subtle section alternation)
- **Borders**: `border-border` (standard), `border-border/40` (very subtle, used for section dividers)
- **Interactive elements**: `bg-foreground text-background` (inverted for buttons)

#### Opacity Usage
| Pattern | Usage |
|---------|-------|
| `bg-primary/5` | Background blobs, very subtle tints |
| `bg-primary/10` | Selected state backgrounds |
| `bg-foreground/5` | Icon containers, subtle fills |
| `bg-foreground/10` | Hover state for icon containers |
| `border-border/40` | Section dividers (subtler than full border) |
| `border-border/50` | Card borders |
| `border-foreground/10` | Testimonial left borders |
| `border-foreground/20` | Highlighted card borders |
| `text-muted-foreground/40` | X icons (negative items), placeholders |
| `opacity-60` | Trust badges, footnote text |
| `shadow-foreground/5` | Card hover shadows |
| `shadow-foreground/20` | Target element shadows |

---

## Typography

### Font Stacks (System Fonts Only)

**Sans-serif (default):**
```
font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
```
This is Tailwind's default — no need to specify a class.

**Monospace:**
```
font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
```
Use `font-mono` class.

### Type Scale — Exact Patterns Used

#### Hero Headline
```
className="text-5xl md:text-7xl font-light tracking-tight leading-[1.1] mb-8"
```
- Mobile: `text-5xl` (3rem / 48px)
- Desktop: `text-7xl` (4.5rem / 72px)
- Weight: **Light (300)** — `font-light` — this is critical
- Tracking: `tracking-tight` (-0.025em)
- Line height: Custom `leading-[1.1]`
- Bottom margin: `mb-8`

#### Hero Subtitle / Secondary Headline Line
```
className="text-muted-foreground"
```
Applied as a `<span>` within the h1 to create two-tone headlines. First line is `text-foreground`, second is `text-muted-foreground`.

#### Section Headline (h2)
```
className="text-3xl md:text-4xl font-light text-center mb-16"
```
- Mobile: `text-3xl` (1.875rem / 30px)
- Desktop: `text-4xl` (2.25rem / 36px)
- Weight: **Light (300)** — always `font-light` for headlines
- Centered for section titles
- Bottom margin: `mb-12` to `mb-16`

#### Large Narrative Text (Problem/Solution blocks)
```
className="text-2xl md:text-3xl font-light leading-relaxed text-muted-foreground"
```
- Size: `text-2xl md:text-3xl`
- Weight: Light (300)
- Line height: `leading-relaxed`
- Color: `text-muted-foreground` with `<span className="text-foreground">` for emphasis words

#### Eyebrow / Section Label
```
className="text-sm font-mono text-muted-foreground mb-4"
```
- Size: `text-sm` (0.875rem / 14px)
- Font: `font-mono` — ALWAYS monospace
- Color: `text-muted-foreground`
- Bottom margin: `mb-4` (sometimes `mb-8`)
- Text is sentence case (not uppercase for eyebrows — e.g., "How it works", "The problem")
- Centered when section is centered: add `text-center`

**Important**: Eyebrows are NOT uppercase in the main sections. They're sentence case in mono font. The only uppercase mono text is in column headers like "Your Team" in flow diagrams:
```
className="text-xs font-mono text-muted-foreground uppercase tracking-wider"
```

#### Subheading / Lead Paragraph
```
className="text-xl text-muted-foreground max-w-xl leading-relaxed mb-12"
```

#### Card Title
```
className="text-xl font-medium mb-3 group-hover:text-primary transition-colors"
```
or
```
className="text-2xl font-medium mb-3 group-hover:text-primary transition-colors"
```

#### Card Description
```
className="text-sm text-muted-foreground leading-relaxed mb-4"
```
or for wider cards:
```
className="text-muted-foreground leading-relaxed"
```

#### Small Labels / Metadata
```
className="text-xs text-muted-foreground"
```

#### Metric Numbers
```
className="text-5xl md:text-6xl font-light tabular-nums"
```
or
```
className="text-3xl md:text-4xl font-light tabular-nums text-primary"
```
Always use `tabular-nums` for numbers that animate or align.

#### Footer Category Labels
```
className="text-xs font-medium uppercase tracking-wider mb-3"
```

### Font Weight Usage Summary

| Weight | Class | Where Used |
|--------|-------|-----------|
| Light (300) | `font-light` | ALL headlines (h1, h2), display numbers, narrative text. This is the signature weight. |
| Regular (400) | (default) | Body text, descriptions, links |
| Medium (500) | `font-medium` | Card titles, button text, labels, names, navigation active states, logo |
| Semibold (600) | `font-semibold` | Almost never used |

### Letter Spacing

| Class | Value | Usage |
|-------|-------|-------|
| `tracking-tight` | -0.025em | Hero headlines |
| `tracking-wider` | 0.05em | Uppercase labels (footer categories, column headers) |
| (default) | 0 | Everything else |

---

## Spacing & Layout

### Section Padding

| Pattern | Tailwind | Pixels | Usage |
|---------|----------|--------|-------|
| Large sections | `py-32 px-6` | 128px / 24px | Hero, features, CTA, flow diagrams, use cases |
| Medium sections | `py-24 px-6` | 96px / 24px | Testimonials, security, secondary sections |
| Compact sections | `py-20 px-6` | 80px / 24px | Integrations marquee |
| Footer | `pt-12 pb-8 px-6` | 48px top, 32px bottom | Footer only |

**Rule**: Every section gets `px-6` horizontal padding. Always.

### Container Widths

| Width | Tailwind | Usage |
|-------|----------|-------|
| `max-w-2xl` | 672px | FAQ, focused text content |
| `max-w-3xl` | 768px | Problem/solution narrative, ROI calculator |
| `max-w-4xl` | 896px | Product demo, comparisons, hero content, security grid |
| `max-w-5xl` | 1024px | Three-column features, use cases, flow diagram, integrations, header/footer |
| `max-w-lg` | 512px | Contact form |

Container pattern: `container mx-auto max-w-{size}`

### Common Spacing Between Elements

| Context | Spacing | Class |
|---------|---------|-------|
| Eyebrow → Headline | 16px | `mb-4` |
| Headline → Content grid | 48-64px | `mb-12` to `mb-16` |
| Headline → Subtitle | 32px | `mb-8` |
| Subtitle → CTAs | 48px | `mb-12` |
| CTA group → Trust badges | 32px | `mt-8` |
| Icon → Step number | 24px | `mb-6` |
| Card title → Description | 12px | `mb-3` |
| Description → Metric | 16px | `mb-4` |
| Grid gap (cards) | 24px | `gap-6` |
| Grid gap (features, wider) | 32-48px | `gap-8` or `gap-12 md:gap-8` |
| FAQ items spacing | 24px | `space-y-6` |
| Testimonial grid gap | 32px | `gap-8` |
| List item spacing | 12px | `space-y-3` |

### Section Dividers
Sections alternate between:
1. No background change, divider line at top: `border-t border-border/40`
2. Background change: `bg-muted/30` (no border needed)

---

## Border, Radius & Shadows

### Border Radius Tokens (CSS Variables)
```css
--radius: 0.625rem;           /* 10px — base */
--radius-sm: calc(0.625rem - 4px);  /* 6px */
--radius-md: calc(0.625rem - 2px);  /* 8px */
--radius-lg: 0.625rem;              /* 10px */
--radius-xl: calc(0.625rem + 4px);  /* 14px */
```

### Radius Usage

| Element | Class | Actual Value |
|---------|-------|-------------|
| Buttons (primary, secondary) | `rounded-full` | Pill shape (9999px) |
| Text inputs | `rounded-full` | Pill shape |
| Textareas | `rounded-2xl` | 16px |
| Cards | `rounded-2xl` | 16px |
| Icon containers | `rounded-xl` | 14px |
| Select buttons (multi-choice) | `rounded-xl` | 14px |
| Integration chips in marquee | `rounded-2xl` | 16px |
| Browser mockup | `rounded-xl` | 14px |
| Avatars / circle elements | `rounded-full` | Circle |
| Badges (result badges) | `rounded-full` | Pill |
| Address bar (mockup) | `rounded-md` | 6px |
| Progress dots | `rounded-full` | Circle |

### Border Patterns

| Pattern | Class |
|---------|-------|
| Standard card border | `border border-border` |
| Highlighted card border | `border-foreground/20 bg-foreground/5` |
| Section divider | `border-t border-border/40` |
| Header bottom | `border-b border-border/40` |
| Footer internal divider | `border-t border-border/40 pt-6` |
| FAQ item divider | `border-b border-border pb-6` |
| Testimonial left accent | `border-l-2 border-foreground/10 pl-5` |
| Featured card (2px) | `border-2 border-foreground` or `border-2 border-border` |
| Focus state | `focus:border-primary/50 focus:ring-2 focus:ring-primary/20` |
| Scroll indicator | `border-2 border-border rounded-full` |

### Shadows

Shadows are used sparingly. The design primarily relies on borders.

| Pattern | Class | Context |
|---------|-------|---------|
| Browser mockup | `shadow-lg` | Product demo container |
| Card hover | `hover:shadow-lg hover:shadow-foreground/5` | Use case cards |
| Highlighted element | `shadow-lg shadow-foreground/20` | Active flow diagram target |
| Button (subtle) | `shadow-xs` | Rare, on specific buttons |

---

## Component Patterns

### Buttons

#### Primary CTA (Hero-level)
```tsx
<motion.a
  href="..."
  className="px-8 py-4 bg-foreground text-background rounded-full font-medium text-lg relative overflow-hidden group"
  whileHover={{ scale: 1.02 }}
  whileTap={{ scale: 0.98 }}
>
  <span className="relative z-10">Book a demo</span>
  <motion.div
    className="absolute inset-0 bg-primary"
    initial={{ x: "-100%" }}
    whileHover={{ x: 0 }}
    transition={{ duration: 0.3 }}
  />
</motion.a>
```
Key traits:
- `px-8 py-4` (generous padding)
- `bg-foreground text-background` (inverted colors)
- `rounded-full` (pill shape)
- `font-medium text-lg`
- Slide-in background on hover
- Scale 1.02 on hover, 0.98 on tap

#### Final CTA (Bigger)
```tsx
className="px-10 py-4 bg-foreground text-background rounded-full font-medium text-lg relative overflow-hidden group"
```
Even more horizontal padding (`px-10`).

#### Secondary / Ghost Button (Text Link Style)
```tsx
<motion.button
  className="px-8 py-4 text-muted-foreground hover:text-foreground transition-colors text-lg flex items-center gap-2"
  whileHover={{ x: 5 }}
>
  See how it works
  <motion.span animate={{ x: [0, 5, 0] }} transition={{ duration: 1.5, repeat: Infinity }}>
    →
  </motion.span>
</motion.button>
```
Key traits:
- No background, no border
- `text-muted-foreground` → `hover:text-foreground`
- Animated arrow that bounces right infinitely
- Whole button shifts right 5px on hover

#### Header CTA (Small)
```tsx
className="text-sm px-4 py-2 bg-foreground text-background rounded-full font-medium hover:opacity-90 transition-opacity"
```

#### Form Navigation Button
```tsx
className="px-8 py-3 bg-primary text-primary-foreground rounded-full font-medium hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
```

#### Back Button (Text)
```tsx
className="text-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-0 disabled:cursor-default"
```
Content: `← Back` (with arrow character)

### Cards

#### Standard Feature/Use Case Card
```tsx
<motion.div
  initial={{ opacity: 0, y: 30 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true }}
  transition={{ delay: i * 0.15, type: "spring", damping: 20 }}
  whileHover={{ y: -8, transition: { duration: 0.2 } }}
  className="p-6 rounded-2xl border border-border bg-background hover:border-foreground/30 hover:shadow-lg hover:shadow-foreground/5 transition-all duration-300 group"
>
  {/* Icon container */}
  <div className="flex items-center gap-3 mb-4">
    <div className="w-10 h-10 rounded-xl bg-foreground/5 flex items-center justify-center group-hover:bg-foreground group-hover:text-background transition-colors">
      <svg className="w-5 h-5" .../>
    </div>
    <p className="text-xs font-mono text-muted-foreground uppercase tracking-wider">{label}</p>
  </div>
  <h3 className="text-xl font-medium mb-3 group-hover:text-primary transition-colors">{title}</h3>
  <p className="text-sm text-muted-foreground leading-relaxed mb-4">{description}</p>
</motion.div>
```
Key traits:
- `p-6 rounded-2xl border border-border bg-background`
- Hover: lifts up 8px (`whileHover={{ y: -8 }}`), border darkens, shadow appears
- Icon container inverts on group hover (`group-hover:bg-foreground group-hover:text-background`)
- Uses `group` class for coordinated hover effects

#### Comparison Column Card
```tsx
<div className={`p-6 rounded-2xl border ${
  highlighted
    ? "border-foreground/20 bg-foreground/5"
    : "border-border"
}`}>
  <h3 className={`text-lg font-medium mb-6 ${highlighted ? "text-primary" : ""}`}>
    {title}
  </h3>
  <ul className="space-y-3">
    <li className="flex items-center gap-2 text-sm">
      {/* Check or X icon */}
      <span className={bad ? "text-muted-foreground" : ""}>{text}</span>
    </li>
  </ul>
</div>
```
- Highlighted column: `border-foreground/20 bg-foreground/5`
- Normal column: `border-border` only
- Check items: `text-emerald-500` icon
- X items: `text-muted-foreground/40` icon, `text-muted-foreground` text

#### Integration Chip (Marquee item)
```tsx
<div className="flex items-center gap-3 px-5 py-3 bg-background border border-border rounded-2xl shrink-0">
  <svg className="w-6 h-6 shrink-0" viewBox="0 0 24 24" fill={color}>
    <path d={svgPath} />
  </svg>
  <span className="text-sm font-medium whitespace-nowrap">{name}</span>
</div>
```

### Section Headers (Consistent Pattern)

Every section follows this exact pattern:
```tsx
<section className="py-32 px-6 border-t border-border/40">
  <div className="container mx-auto max-w-{size}">
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
    >
      <p className="text-sm font-mono text-muted-foreground mb-4 text-center">
        Eyebrow text
      </p>
      <h2 className="text-3xl md:text-4xl font-light text-center mb-16">
        Headline goes here
      </h2>
      {/* Content */}
    </motion.div>
  </div>
</section>
```

### Form Inputs

#### Text Input (Pill)
```tsx
<input
  className="w-full px-5 py-4 text-base bg-background border border-border rounded-full outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20 transition-all placeholder:text-muted-foreground/40"
/>
```
- Height achieved through `py-4` (approximately 56px total)
- `rounded-full` — always pill shaped
- Focus: border becomes `primary/50`, ring is `primary/20`
- Placeholder opacity: 40%

#### Textarea
```tsx
<textarea
  rows={4}
  className="w-full px-5 py-4 text-base bg-background border border-border rounded-2xl outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20 transition-all placeholder:text-muted-foreground/40 resize-none"
/>
```
Same as text input but `rounded-2xl` instead of `rounded-full`, and `resize-none`.

#### Select Buttons (Grid of Options)
```tsx
<div className="grid grid-cols-2 gap-3">
  <motion.button
    whileHover={{ scale: 1.02 }}
    whileTap={{ scale: 0.98 }}
    className={`px-4 py-3 rounded-xl border text-sm font-medium transition-all ${
      selected
        ? "border-primary bg-primary/10 text-primary"
        : "border-border hover:border-border/80 text-muted-foreground hover:text-foreground"
    }`}
  >
    {label}
  </motion.button>
</div>
```

#### Range Slider
```tsx
<input
  type="range"
  className="w-full h-1.5 bg-border rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-foreground [&::-webkit-slider-thumb]:cursor-pointer"
/>
```

### Progress Indicators

#### Step Progress Bar (Multi-step form)
```tsx
<div className="flex items-center justify-center gap-2 mb-10">
  {steps.map((_, i) => (
    <div
      key={i}
      className={`h-1.5 rounded-full transition-all duration-300 ${
        i <= currentStep ? "w-8 bg-primary" : "w-3 bg-border/50"
      }`}
    />
  ))}
</div>
```

#### Flow Diagram Step Indicators
```tsx
<div className="flex gap-2">
  {[0, 1, 2, 3].map((step) => (
    <button
      className={`h-1.5 rounded-full transition-all duration-300 hover:bg-muted-foreground ${
        active === step ? "w-8 bg-foreground" : "w-2 bg-border"
      }`}
    />
  ))}
</div>
```

### Header / Navigation

```tsx
<header className="sticky top-0 z-50 bg-background/80 backdrop-blur-sm border-b border-border/40">
  <div className="container mx-auto px-6 py-4 max-w-5xl flex items-center justify-between">
    {/* Logo on left */}
    <Link className="text-lg font-mono font-medium hover:opacity-70 transition-opacity">
      [simulation labs]
    </Link>
    {/* Nav + CTA on right */}
    <nav className="hidden sm:flex items-center gap-6">
      <Link className="text-sm text-muted-foreground hover:text-foreground transition-colors">
        Link
      </Link>
      <a className="text-sm px-4 py-2 bg-foreground text-background rounded-full font-medium hover:opacity-90 transition-opacity">
        Book Demo
      </a>
    </nav>
  </div>
</header>
```
- `sticky top-0 z-50`
- `bg-background/80 backdrop-blur-sm` (glass morphism)
- `border-b border-border/40`
- Desktop nav: `hidden sm:flex items-center gap-6`
- Nav links: `text-sm`, muted by default, foreground on hover/active

### Footer

```tsx
<footer className="border-t border-border/40 pt-12 pb-8 px-6">
  <div className="container mx-auto max-w-5xl">
    <div className="flex flex-col md:flex-row justify-between items-start gap-8 mb-10">
      {/* Brand + tagline */}
      <div>
        <span className="font-mono text-sm">[simulation labs]</span>
        <p className="text-sm text-muted-foreground mt-2 max-w-xs">Tagline text here.</p>
      </div>
      {/* Link columns */}
      <div className="flex flex-col sm:flex-row gap-8">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider mb-3">Category</p>
          <div className="flex flex-col gap-2 text-sm text-muted-foreground">
            <Link className="hover:text-foreground transition-colors">Link</Link>
          </div>
        </div>
      </div>
    </div>
    {/* Bottom bar */}
    <div className="border-t border-border/40 pt-6 flex flex-col sm:flex-row justify-between items-center gap-4 text-xs text-muted-foreground">
      <p>© 2026 Simulation Labs, Inc.</p>
      <p>Built in West Lafayette, IN</p>
    </div>
  </div>
</footer>
```

### Testimonials

```tsx
<div className="border-l-2 border-foreground/10 pl-5">
  <p className="text-sm leading-relaxed text-muted-foreground mb-4">"{quote}"</p>
  <div>
    <p className="text-sm font-medium">{name}</p>
    <p className="text-xs text-muted-foreground">{title}, {company}</p>
  </div>
</div>
```

### FAQ Items

```tsx
<div className="border-b border-border pb-6">
  <h3 className="font-medium mb-2">{question}</h3>
  <p className="text-sm text-muted-foreground leading-relaxed">{answer}</p>
</div>
```
Wrapped in `space-y-6` container.

### Trust Badges (Below CTAs)

```tsx
<div className="flex flex-wrap items-center gap-4 mt-8 opacity-60">
  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="..." />
    </svg>
    Label text
  </span>
</div>
```
- `opacity-60` on the whole container — they should be subtle
- Icon: `w-3.5 h-3.5`, `strokeWidth={1.5}`

### Live Indicator (Pulsing Dot)

```tsx
<div className="flex items-center gap-2">
  <motion.div
    className="w-2 h-2 rounded-full bg-emerald-500"
    animate={{ scale: [1, 1.2, 1] }}
    transition={{ duration: 2, repeat: Infinity }}
  />
  <p className="text-sm font-mono text-muted-foreground">Label text</p>
</div>
```

### Scroll Indicator (Mouse icon)

```tsx
<motion.div
  animate={{ y: [0, 8, 0] }}
  transition={{ duration: 2, repeat: Infinity }}
  className="w-6 h-10 border-2 border-border rounded-full flex justify-center pt-2"
>
  <motion.div
    className="w-1 h-2 bg-muted-foreground rounded-full"
    animate={{ y: [0, 4, 0], opacity: [1, 0.5, 1] }}
    transition={{ duration: 2, repeat: Infinity }}
  />
</motion.div>
```

### Browser Mockup (Product Demo)

```tsx
<div className="rounded-xl border border-border overflow-hidden bg-background shadow-lg">
  {/* Top bar */}
  <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-muted/30">
    <div className="flex gap-1.5">
      <div className="w-3 h-3 rounded-full bg-border" />
      <div className="w-3 h-3 rounded-full bg-border" />
      <div className="w-3 h-3 rounded-full bg-border" />
    </div>
    <div className="flex-1 mx-8 h-6 rounded-md bg-background border border-border flex items-center px-3">
      <span className="text-xs text-muted-foreground">app.simulationlabs.io</span>
    </div>
  </div>
  {/* Content area */}
  <div className="w-full">
    {/* ... */}
  </div>
</div>
```

### Success State

```tsx
<motion.div
  initial={{ scale: 0 }}
  animate={{ scale: 1 }}
  transition={{ type: "spring", damping: 15, delay: 0.1 }}
  className="w-16 h-16 mx-auto mb-6 rounded-full bg-primary/10 flex items-center justify-center"
>
  <svg className="w-8 h-8 text-primary" ...>
    <path d="M5 13l4 4L19 7" />
  </svg>
</motion.div>
<h2 className="text-2xl md:text-3xl font-light mb-3">Success message</h2>
<p className="text-muted-foreground mb-8">Subtitle text.</p>
```

### Loading Spinner

```tsx
<motion.div
  animate={{ rotate: 360 }}
  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
  className="w-4 h-4 border-2 border-white border-t-transparent rounded-full"
/>
```

---

## Animation & Motion

### Framework
All animation uses **Framer Motion** (`framer-motion`). No CSS animation for component-level motion (CSS keyframes only for background effects).

### Standard Entrance Animation (Most Common)
```tsx
initial={{ opacity: 0, y: 20 }}
whileInView={{ opacity: 1, y: 0 }}
viewport={{ once: true }}
```
- `y: 20` → `y: 0` (slides up 20px while fading in)
- `viewport={{ once: true }}` — ALWAYS. Never re-animate on scroll.
- No explicit duration (uses Framer Motion defaults ~0.3-0.5s)

### Hero Entrance (Staggered)
```tsx
// Container: fade in
initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1 }}

// Elements stagger with delay:
// Eyebrow:  delay: 0.2
// Headline line 1: delay: 0.4
// Headline line 2: delay: 0.5
// Subtitle: delay: 0.6
// CTAs: delay: 0.8
// Trust badges: delay: 1.1
// Scroll indicator: delay: 1.5
```

### Staggered Children
```tsx
{items.map((item, i) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true }}
    transition={{ delay: i * 0.1 }}  // or i * 0.15
  />
))}
```
Stagger delay: `0.1` to `0.15` per item.

### Larger Entrance (Narrative Sections)
```tsx
initial={{ opacity: 0, y: 40 }}
whileInView={{ opacity: 1, y: 0 }}
viewport={{ once: true }}
transition={{ duration: 0.8 }}
```
Uses `y: 40` and explicit `duration: 0.8` for slower, more dramatic reveal.

### Hover States

| Element | Motion | Value |
|---------|--------|-------|
| Primary CTA button | Scale up | `whileHover={{ scale: 1.02 }}` |
| Final CTA button | Scale up more | `whileHover={{ scale: 1.05 }}` |
| Cards | Lift up | `whileHover={{ y: -8 }}` (or `y: -5`) |
| Feature items | Lift up | `whileHover={{ y: -5 }}` |
| Text links with arrow | Shift right | `whileHover={{ x: 5 }}` |
| Icon container | Wobble | `whileHover={{ rotate: [0, -5, 5, 0] }}` with `transition={{ duration: 0.5 }}` |
| Select buttons | Scale | `whileHover={{ scale: 1.02 }}` |
| Avatar circles | Scale | `whileHover={{ scale: 1.05 }}` |

### Tap States
All clickable elements: `whileTap={{ scale: 0.98 }}` or `whileTap={{ scale: 0.95 }}`

### Animated Arrow (Bouncing)
```tsx
<motion.span
  animate={{ x: [0, 5, 0] }}
  transition={{ duration: 1.5, repeat: Infinity }}
>
  →
</motion.span>
```

### Infinite Pulse (Live Indicator)
```tsx
animate={{ scale: [1, 1.2, 1] }}
transition={{ duration: 2, repeat: Infinity }}
```

### Animated Counter
Counts up from 0 to target number when scrolled into view. Uses easeOutCubic easing (`1 - Math.pow(1 - progress, 3)`). Duration: 1.5 seconds. Uses `requestAnimationFrame`-style 16ms interval.

### AnimatePresence for Step Transitions
```tsx
<AnimatePresence mode="wait">
  <motion.div
    key={step}
    initial={{ opacity: 0, x: 20 }}
    animate={{ opacity: 1, x: 0 }}
    exit={{ opacity: 0, x: -20 }}
    transition={{ duration: 0.2 }}
  >
    {/* Step content */}
  </motion.div>
</AnimatePresence>
```
Direction: enters from right (x: 20), exits to left (x: -20).

### Spring Animations
```tsx
transition={{ type: "spring", damping: 15 }}  // bouncy
transition={{ type: "spring", damping: 20 }}  // moderate
transition={{ type: "spring" }}                // default spring
```
Used for: result badges appearing, scale animations, staggered dots.

### Transition Durations Summary

| Duration | Usage | CSS/Framer |
|----------|-------|------------|
| 0.15s | Micro interactions (color changes) | `transition-colors` |
| 0.2s | Step transitions (AnimatePresence) | Framer `duration: 0.2` |
| 0.3s | Standard transitions | `transition-all duration-300` |
| 0.5s | Element entrances, icon wobble | Framer `duration: 0.5` |
| 0.8s | Hero elements, narrative reveals | Framer `duration: 0.8` |
| 1.0s | Full page fade-in | Framer `duration: 1` |
| 1.5s | Animated counters, bouncing arrows | Framer loops |
| 2.0s | Pulsing indicators | Framer infinite loops |

---

## Background & Decorative Effects

### Animated Gradient Blobs
```tsx
<div className="absolute inset-0 -z-10">
  <motion.div
    className="absolute top-1/4 -left-1/4 w-1/2 h-1/2 rounded-full bg-primary/5 blur-3xl"
    animate={{ x: [0, 50, 0], y: [0, 30, 0] }}
    transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
  />
  <motion.div
    className="absolute bottom-1/4 -right-1/4 w-1/2 h-1/2 rounded-full bg-primary/5 blur-3xl"
    animate={{ x: [0, -50, 0], y: [0, -30, 0] }}
    transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
  />
</div>
```
Key traits:
- Two blobs, opposite corners
- `bg-primary/5` — very low opacity (5%)
- `blur-3xl` — extremely blurred
- Movement: 20-25 second full cycle
- Displacement: 30-50px total
- `ease: "easeInOut"` — smooth, slow
- Parent must have `relative overflow-hidden`
- Blobs have `-z-10` to sit behind content

### CTA Section Background Blob
```tsx
<motion.div
  className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-primary/5 blur-3xl"
  animate={{ scale: [1, 1.2, 1], opacity: [0.3, 0.5, 0.3] }}
  transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
/>
```
Single centered blob that breathes (scales and pulses opacity).

### CRT Scanline Effect
Applied via `.crt` CSS class on a section container.

```css
.crt {
  position: relative;
  overflow: hidden;
  background: var(--background);
}
.crt > * { position: relative; z-index: 1; }

/* Scanlines */
.crt::before {
  content: "";
  position: absolute; inset: 0;
  background: linear-gradient(transparent 95%, color-mix(in oklch, var(--foreground), transparent 80%) 100%);
  background-size: 100% 4px;
  opacity: 0.18;
  animation: crt-scan 6s linear infinite;
  pointer-events: none; z-index: 0;
}

/* Radial glow */
.crt::after {
  content: "";
  position: absolute; inset: 0;
  background: radial-gradient(circle at 20% 20%, color-mix(in oklch, var(--foreground), transparent 90%), transparent 45%);
  mix-blend-mode: soft-light;
  opacity: 0.35;
  animation: crt-flicker 4s steps(2) infinite;
  pointer-events: none; z-index: 0;
}
```

### Text Glow
```css
.text-glow {
  text-shadow: 0 0 12px color-mix(in oklch, var(--primary), transparent 60%);
}
```

### Shimmer Button Effect

#### Light variant (border shimmer)
```css
.shimmer-button {
  position: relative; overflow: hidden;
}
.shimmer-button::before {
  content: ""; position: absolute; inset: -2px;
  background: conic-gradient(from 0deg, transparent 0deg, transparent 60deg, hsl(var(--primary) / 0.6) 90deg, hsl(var(--primary) / 0.8) 120deg, hsl(var(--primary) / 0.6) 150deg, transparent 180deg, transparent 360deg);
  border-radius: 9999px;
  animation: shimmer-rotate 3s linear infinite;
}
.shimmer-button::after {
  content: ""; position: absolute; inset: 1px;
  background: var(--background); border-radius: 9999px;
}
```

#### Dark variant (white light traveling on black border)
```css
.shimmer-button-dark {
  position: relative; overflow: hidden;
  background: var(--background);
  border: 2px solid hsl(var(--foreground));
}
.shimmer-button-dark::before {
  content: ""; position: absolute; inset: -3px;
  background: conic-gradient(from 0deg, transparent 0deg, transparent 70deg, rgba(255,255,255,0.8) 85deg, rgba(255,255,255,1) 90deg, rgba(255,255,255,0.8) 95deg, transparent 110deg, transparent 360deg);
  border-radius: 9999px;
  animation: shimmer-rotate 2s linear infinite;
}
.shimmer-button-dark::after {
  content: ""; position: absolute; inset: 2px;
  background: var(--background); border-radius: 9999px;
}
```

### Infinite Marquee (Integration Logos)
```css
@keyframes marquee-left {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
@keyframes marquee-right {
  0% { transform: translateX(-50%); }
  100% { transform: translateX(0); }
}
```

Usage:
```tsx
<div
  className="group relative overflow-hidden"
  style={{
    maskImage: "linear-gradient(to right, transparent, black 8%, black 92%, transparent)",
    WebkitMaskImage: "linear-gradient(to right, transparent, black 8%, black 92%, transparent)",
  }}
>
  <div
    className="flex gap-4 w-max group-hover:[animation-play-state:paused]"
    style={{ animation: "marquee-left 40s linear infinite" }}
  >
    {/* Duplicate items array to create seamless loop */}
    {[...items, ...items].map((item, i) => (
      <div key={i} className="...">...</div>
    ))}
  </div>
</div>
```
- Row 1: `marquee-left 40s`
- Row 2: `marquee-right 45s`
- Edge fade: CSS mask-image gradient (transparent → black 8% → black 92% → transparent)
- Pause on hover: `group-hover:[animation-play-state:paused]`

### Alternating Section Backgrounds

| Pattern | Usage |
|---------|-------|
| `bg-background` (no class needed) | Default sections |
| `bg-muted/30` | "How it works", Integrations, Security — creates subtle stripe |

---

## Iconography

### Library
**Inline SVGs** — not a component library. Icons are written directly as `<svg>` elements with path data.

### Standard Icon Props
```tsx
<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="..." />
</svg>
```

| Property | Value |
|----------|-------|
| `fill` | `"none"` (stroke icons, not filled) |
| `stroke` | `"currentColor"` (inherits text color) |
| `viewBox` | `"0 0 24 24"` |
| `strokeLinecap` | `"round"` |
| `strokeLinejoin` | `"round"` |
| `strokeWidth` | `1.5` (standard) or `2` (bold, for check/X marks) |

### Icon Sizes

| Size | Class | Context |
|------|-------|---------|
| 12px | `w-3 h-3` | External link indicators |
| 14px | `w-3.5 h-3.5` | Trust badge icons, small inline |
| 16px | `w-4 h-4` | List item icons (checks, X marks), inline with text, navigation arrows |
| 20px | `w-5 h-5` | Default size, card icons, nav hamburger |
| 24px | `w-6 h-6` | Feature section icons, integration logos |
| 32px | `w-8 h-8` | Success state large icon |

### Check Mark Icon
```tsx
<svg className="w-4 h-4 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
</svg>
```

### X Mark Icon (Negative)
```tsx
<svg className="w-4 h-4 text-muted-foreground/40 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
</svg>
```

### Right Arrow (Inline Link)
```tsx
<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
</svg>
```

### External Link Icon
```tsx
<svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
</svg>
```

---

## Responsive Behavior

### Breakpoints (Tailwind defaults)
| Name | Width | Usage |
|------|-------|-------|
| `sm` | 640px | Side-by-side CTAs, footer columns, desktop nav shows |
| `md` | 768px | 2-3 column grids, larger typography |
| `lg` | 1024px | Rarely used |
| `xl` | 1280px | Rarely used |

### Mobile-First Typography Scaling

| Element | Mobile | Desktop |
|---------|--------|---------|
| Hero h1 | `text-5xl` (48px) | `md:text-7xl` (72px) |
| Section h2 | `text-3xl` (30px) | `md:text-4xl` (36px) |
| Smaller h2 | `text-2xl` (24px) | `md:text-3xl` (30px) |
| Metric numbers | `text-5xl` (48px) | `md:text-6xl` (60px) |
| ROI metric | `text-3xl` (30px) | `md:text-4xl` (36px) |
| CTA headline | `text-4xl` (36px) | `md:text-5xl` (48px) |

### Grid Responsive Patterns
```tsx
// 3-column → 1-column on mobile
className="grid md:grid-cols-3 gap-6"

// 4-column → 2-column on mobile
className="grid sm:grid-cols-2 md:grid-cols-4 gap-6"

// 3-column with different mobile gap
className="grid md:grid-cols-3 gap-12 md:gap-8"
```

### CTA Layout
```tsx
// Stack on mobile, row on tablet+
className="flex flex-col sm:flex-row items-start gap-4"

// Centered variant
className="flex flex-col sm:flex-row items-center justify-center gap-4"
```

### Mobile Navigation
- Desktop nav: `hidden sm:flex items-center gap-6`
- Hamburger: `sm:hidden`
- Mobile menu panel: `sm:hidden border-t border-border/40 bg-background/95 backdrop-blur-sm px-6 py-4 space-y-3`

### Hidden on Mobile
Some secondary info is hidden on small screens:
```tsx
<div className="hidden sm:block">
  <p className="text-sm font-medium">{name}</p>
  <p className="text-xs text-muted-foreground">{role}</p>
</div>
```

---

## Voice & Tone

### Writing Rules
1. **Sentence case always** — "How it works" not "How It Works"
2. **Short headlines** — under 8 words. "Your team's network, one search away."
3. **Active voice** — "Simulation Labs finds" not "Connections are found by"
4. **Present tense** — "Find anyone" not "You will find anyone"
5. **Direct address** — "your team", "your network"

### Headline Patterns
- Two-line hero with contrast: line 1 is `text-foreground`, line 2 is `text-muted-foreground`
- Example: "Your team's network," / "one search away."
- Section headlines state the benefit: "From scattered contacts to warm intros"

### Eyebrow Labels (Above Every Section)
Always sentence case, short (2-3 words):
- "How it works"
- "Why Simulation Labs"
- "Use cases"
- "The math"
- "The principle"
- "Integrations"
- "Security"
- "FAQ"
- "See it in action"
- "Calculate your network"

### Button Copy
- Primary CTA: "Book a demo", "Book a team demo"
- Secondary: "See how it works →"
- Form: "Next", "Send Message", "← Back"
- Links: "Learn more about our security practices →"

### Metric Labels
- Always below the number
- `text-xs text-muted-foreground mt-2`
- Descriptive: "team members", "connections each", "searchable relationships"

---

## Anti-Patterns

**DO NOT do any of these:**

1. **No colorful gradients** — no blue-to-purple, no rainbow effects. Only achromatic + emerald accent.
2. **No heavy font weights for headlines** — never use `font-bold` or `font-semibold` for h1/h2. Always `font-light` (300).
3. **No small border radius on buttons** — buttons are always `rounded-full` (pill). Never `rounded-md` or `rounded-lg` on a button.
4. **No card backgrounds that stand out** — cards use `bg-background` with subtle border, not `bg-muted` or `bg-card` as a colored fill.
5. **No thick borders** — standard borders are 1px (`border`). Only featured elements or focus states use 2px (`border-2`).
6. **No box shadows by default** — shadows only appear on hover or on special elements (browser mockup). Cards don't have shadows at rest.
7. **No emoji** in the UI.
8. **No decorative illustrations** or blob shapes in content areas.
9. **No underlined links by default** — links use color transitions, not underlines.
10. **No centered body text** — paragraphs/descriptions are left-aligned. Only headlines, eyebrows, and footer text are centered.
11. **No custom web fonts** — system font stack only.
12. **No uppercase eyebrows in main sections** — eyebrow text is sentence case in `font-mono`. Uppercase is only used for very small structural labels like footer categories and column headers.
13. **No generic hero backgrounds** — no stock photo, no generic grid pattern. Background is either plain white/dark or has the animated blobs described above.
14. **No button outlines/ghost buttons with borders for primary CTAs** — primary buttons are always solid `bg-foreground text-background`.
15. **No hover:scale-110 or larger** — hover scale is always subtle: 1.02 for buttons, 1.05 at most for circles.
16. **No bright accent colors** — emerald is the only accent. No blue, purple, orange, or yellow in the UI.
17. **No drop shadows on text** (except the specific `.text-glow` utility).
18. **No padding less than px-6 on sections** — always maintain 24px horizontal padding.
19. **No gap-1 or gap-0.5 between cards** — minimum card gap is `gap-6` (24px).
20. **No animated entrances that repeat on scroll** — always use `viewport={{ once: true }}`.

---

## Complete Code Examples

### Full Section Template
```tsx
<section className="py-32 px-6 border-t border-border/40">
  <div className="container mx-auto max-w-5xl">
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
    >
      <p className="text-sm font-mono text-muted-foreground mb-4 text-center">
        Section label
      </p>
      <h2 className="text-3xl md:text-4xl font-light text-center mb-16">
        Section headline here
      </h2>

      <div className="grid md:grid-cols-3 gap-6">
        {items.map((item, i) => (
          <motion.div
            key={item.id}
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.15, type: "spring", damping: 20 }}
            whileHover={{ y: -8, transition: { duration: 0.2 } }}
            className="p-6 rounded-2xl border border-border bg-background hover:border-foreground/30 hover:shadow-lg hover:shadow-foreground/5 transition-all duration-300 group"
          >
            <div className="w-10 h-10 rounded-xl bg-foreground/5 flex items-center justify-center mb-4 group-hover:bg-foreground group-hover:text-background transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={item.icon} />
              </svg>
            </div>
            <h3 className="text-xl font-medium mb-3 group-hover:text-primary transition-colors">
              {item.title}
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {item.description}
            </p>
          </motion.div>
        ))}
      </div>
    </motion.div>
  </div>
</section>
```

### Full Page Shell
```tsx
<div className="min-h-screen bg-background text-foreground">
  <SiteHeader />

  {/* Hero */}
  <section className="min-h-screen flex flex-col justify-center px-6 pt-20 relative overflow-hidden">
    <div className="absolute inset-0 -z-10">
      {/* Background blobs */}
    </div>
    <div className="container mx-auto max-w-4xl">
      {/* Hero content */}
    </div>
  </section>

  {/* Sections */}
  <section className="py-32 px-6 border-t border-border/40">...</section>
  <section className="py-32 px-6 bg-muted/30">...</section>
  <section className="py-32 px-6 border-t border-border/40">...</section>

  <footer className="border-t border-border/40 pt-12 pb-8 px-6">...</footer>
</div>
```

### Full Hero Section
```tsx
<section className="min-h-screen flex flex-col justify-center px-6 pt-20 relative overflow-hidden">
  {/* Animated background */}
  <div className="absolute inset-0 -z-10">
    <motion.div
      className="absolute top-1/4 -left-1/4 w-1/2 h-1/2 rounded-full bg-primary/5 blur-3xl"
      animate={{ x: [0, 50, 0], y: [0, 30, 0] }}
      transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
    />
    <motion.div
      className="absolute bottom-1/4 -right-1/4 w-1/2 h-1/2 rounded-full bg-primary/5 blur-3xl"
      animate={{ x: [0, -50, 0], y: [0, -30, 0] }}
      transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
    />
  </div>

  <div className="container mx-auto max-w-4xl">
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1 }}>
      {/* Eyebrow with live dot */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="flex items-center gap-2 mb-6"
      >
        <motion.div
          className="w-2 h-2 rounded-full bg-emerald-500"
          animate={{ scale: [1, 1.2, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
        <p className="text-sm font-mono text-muted-foreground">Eyebrow text</p>
      </motion.div>

      {/* Two-tone headline */}
      <motion.h1
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, duration: 0.8 }}
        className="text-5xl md:text-7xl font-light tracking-tight leading-[1.1] mb-8"
      >
        <span>First line of headline,</span>
        <br />
        <span className="text-muted-foreground">second line muted.</span>
      </motion.h1>

      {/* Subhead */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6 }}
        className="text-xl text-muted-foreground max-w-xl leading-relaxed mb-12"
      >
        Supporting description text goes here.
      </motion.p>

      {/* CTAs */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.8 }}
        className="flex flex-col sm:flex-row items-start gap-4"
      >
        <motion.a
          href="..."
          className="px-8 py-4 bg-foreground text-background rounded-full font-medium text-lg"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          Primary CTA
        </motion.a>
        <motion.button
          className="px-8 py-4 text-muted-foreground hover:text-foreground transition-colors text-lg flex items-center gap-2"
          whileHover={{ x: 5 }}
        >
          Secondary CTA
          <motion.span animate={{ x: [0, 5, 0] }} transition={{ duration: 1.5, repeat: Infinity }}>→</motion.span>
        </motion.button>
      </motion.div>

      {/* Trust badges */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.1 }}
        className="flex flex-wrap items-center gap-4 mt-8 opacity-60"
      >
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="..." />
          </svg>
          Badge text
        </span>
      </motion.div>
    </motion.div>
  </div>

  {/* Scroll indicator */}
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    transition={{ delay: 1.5 }}
    className="absolute bottom-8 left-1/2 -translate-x-1/2"
  >
    <motion.div
      animate={{ y: [0, 8, 0] }}
      transition={{ duration: 2, repeat: Infinity }}
      className="w-6 h-10 border-2 border-border rounded-full flex justify-center pt-2"
    >
      <motion.div
        className="w-1 h-2 bg-muted-foreground rounded-full"
        animate={{ y: [0, 4, 0], opacity: [1, 0.5, 1] }}
        transition={{ duration: 2, repeat: Infinity }}
      />
    </motion.div>
  </motion.div>
</section>
```

---

## Technical Stack Reference

| Tool | Version | Purpose |
|------|---------|---------|
| React | 19.x | UI framework |
| Vite | Latest | Build tool |
| Tailwind CSS | 4.x | Styling (CSS v4 with native nesting) |
| Framer Motion | 12.x | Animation |
| Radix UI | Latest | Accessible primitives (via shadcn/ui "new-york" style) |
| next-themes | Latest | Dark mode |
| react-router | 7.x | Routing |
| react-intersection-observer | Latest | Scroll-triggered animations |

### Base CSS Setup (index.css)
```css
@import "tailwindcss";
@import "tw-animate-css";
@custom-variant dark (&:is(.dark *));

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground;
  }
  button:not([disabled]),
  [role="button"]:not([disabled]) {
    cursor: pointer;
  }
}
```

---

*Last updated: February 2026*
