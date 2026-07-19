# Onboarding research — how viral OSS dev tools reduce time-to-first-"holy shit"

> Phase 1–2 deliverable. **Nothing in the README or CLI has been changed.** This
> doc reports what the viral tools do, where we add friction they don't, and a
> ranked set of proposals for your review. Implementation (Phase 3) waits for your
> approval. New-capability items are flagged as such per the mission constraint.

## Method

Read the current READMEs of 8 dev tools that went viral on GitHub (AI/agent-heavy):
**Ollama, uv, Playwright, LangChain, Aider, Browser-use, Open-Interpreter,
Supermemory.** For each: words before the first code block, commands until
something *visibly works*, where the demo visual sits, and whether a key/account
is required.

## The data

| Tool | Words before 1st code block | Commands to visible result | Demo visual placement | API key needed? |
|---|---|---|---|---|
| **Ollama** | ~110 | **1** (`curl … \| sh`) | logo only, no GIF | **No** |
| **Open-Interpreter** | ~180 | **2** (install → `i`) | ~25% down | key, but deferred |
| **uv** | ~280 | ~3 (`init`→`add`→`run`) | benchmark chart, very top | **No** |
| **Playwright** | ~280 | 3 (`init`→`install`→`test`) | none (TODOs) | **No** |
| **LangChain** | ~280 | 2 (install → run) | none | Yes (assumed) |
| **Aider** | ~290 | 4 (install→install→cd→run) | screencast, **above 1st code** | Yes (assumed) |
| **Browser-use** | ~650 | 3 (install→env→python) | GIFs, **above 1st code** | Yes (assumed) |
| **Supermemory** | ~650 | 1 (`curl … \| bash`) | screenshots ~25% down | key for hosted |

## The common pattern: **hook → one visible win → depth**

Every one of them, regardless of length, follows the same spine:

1. **One-line value prop** in the first screenful — no preamble.
2. **Visual proof high up** — a GIF, screencast, or benchmark chart, usually
   *above or at* the first code block (Aider, Browser-use, uv), never buried.
3. **Exactly one quickstart block** that gets to a visible result, then depth
   (config, features, CI) comes *after*.
4. **The visible win is the whole game.** The tools that truly exploded —
   **Ollama (1 command) and uv (no key, instant)** — get you to a working,
   visible result with the *fewest* commands and *zero credentials*. Friction and
   virality are inversely correlated.

The single sharpest correlation in the data: **the biggest breakouts need no API
key and no account.** Ollama runs a local model; uv is a package manager;
Playwright is a browser driver. None make you leave the terminal to go create a
credential before the first win.

## Where we stand today

Our README already gets the *structure* right:

- ✅ Hero tagline + **animated `sim try` GIF above the fold** (line 7), first code
  block at line 32 — visual-proof-before-code, exactly the viral pattern.
- ✅ 198 words before the first code block — mid-pack, leaner than Aider/Browser-use.
- ✅ "hook → quickstart → depth" spine is intact.

Where we add friction the viral tools don't:

## The 5 gaps (ranked by impact on time-to-first-"holy shit")

**Gap 1 — We require an API key; the biggest breakouts don't.** This is
structural, not cosmetic. Our first win is gated behind "go to aistudio.google.com,
create a key, come back, `export` it." That is a context-switch *out of the
terminal* — the exact friction Ollama/uv/Playwright avoid entirely. Everything
below is downstream of this.

**Gap 2 — 4 commands + a browser download to first result.** Our quickstart is
`pip install` → `playwright install chromium` → `export KEY` → `sim try`. That's
heavier than Ollama (1) or Open-Interpreter (2), and one of the four
(`playwright install chromium`) downloads ~150MB before anything happens.

**Gap 3 — `sim try` doesn't self-heal a missing browser.** If a user runs
`pip install` then `sim try` and skips the chromium step, they hit a raw
Playwright "executable doesn't exist" error instead of a one-line fix or an
auto-install. Viral tools' first command *just works*.

**Gap 4 — the payoff isn't instant.** Even after setup, a real run waits on model
latency (Holo free tier ~5 RPM → minutes; Gemini faster but rate-limited). Ollama
and uv give feedback in seconds. Our "holy shit" arrives a beat late.

**Gap 5 — the generality is invisible.** `--task` is already free-text and
flow-agnostic, but the README shows only signup, so a reader pattern-matches us to
"a signup tester," not "point it at *any* flow." We under-sell what already works.

## Proposals (for your review — not yet implemented)

Ordered by leverage. Each tagged **[docs/flow]** (safe, reversible) or
**[new capability]** (per your constraint, flagged for a decision, not built).
**CI-contract note:** `sim gate --url/--task` and its exit codes are the
paid/enterprise surface. **None of the proposals below change `sim gate`** — they
all touch `sim try` and the README only. I will call out any exception explicitly.

- **P1 — Make the free-Gemini path THE quickstart, not an aside. [docs/flow]**
  Lead with the exact 3-step: "① get a free key (link) → ② paste it → ③ `sim try`,"
  instead of "bring any key you already have." Reduces Gap 1's cognitive load
  without new code. Highest safe leverage.

- **P2 — `sim try` auto-installs Chromium if missing. [flow, sim try only]**
  Detect the missing browser and either auto-run `playwright install chromium`
  with a one-line notice, or print the exact fix. Removes a command (Gap 2) and
  kills the cryptic error (Gap 3). Does not touch `sim gate`.

- **P3 — `sim try` accepts a pasted key interactively. [flow, sim try only]**
  If no key is set, prompt "paste a Gemini key (free — get one at …)" and proceed,
  instead of erroring and asking the user to `export`. Collapses Gap 2's `export`
  step into the run itself. Does not touch `sim gate` (CI must stay non-interactive).

- **P4 — Make generality visible. [docs]** Show 3–4 diverse `--task` examples
  (onboarding wizard, multi-step form, dashboard config, checkout) as a small grid,
  proving "any flow" with the engine we already have. No new capability.

- **P5 — Zero-key instant demo. [NEW CAPABILITY — flagged, not built]**
  The dream first-run is `sim try` with *no key* that still shows five agents
  visibly attempting the real page and one abandoning at the checkbox — then upsells
  "add a free key to drive a real AI agent." **This needs new capability:** the
  existing `echo` backend is intentionally dumb (fixed click at 100,100, ignores the
  screenshot), so it produces no differential success/abandon story. Delivering this
  means a new bundled "replay" backend that reproduces a recorded, verified run
  against the real browser. Per your constraint, I'm **flagging this, not building
  it** — but it is the single highest-leverage fix for Gap 1 and Gap 4, and worth a
  yes/no from you.

- **P6 — Hosted "try-it-now" sandbox (no install, no key). [NEW CAPABILITY / infra — flagged]**
  A page on simulationlabs.dev with a "Run" button that streams a swarm live. Kills
  Gaps 1–4 outright for first-touch, at the cost of a hosted backend + abuse/cost
  controls. Biggest build; pure stretch. Flagged, not scoped.

## Recommendation

Ship **P1–P4** (all [docs/flow], all safe, none touch the `sim gate` CI contract) —
they cut our first-run from "4 commands + leave the terminal for a key" toward
"install → paste key → watch it," and make the any-flow generality visible.

**P5 (zero-key replay demo) is the highest-leverage idea in this doc, but it is new
capability, so I'm stopping to ask** rather than building it. If you want the
first-run to need *zero* credentials — the thing that most separates the viral
breakouts from everyone else — P5 is how, and I'd want your go-ahead first.

Awaiting your review before any Phase 3 changes.
