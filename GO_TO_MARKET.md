# Simulation Labs — Go-To-Market

> Internal, decision-ready GTM doc. Grounded in the real repo (VISION.md, CLAUDE.md,
> `web/src/`, `personas/`, `src/ghostpanel/`), not aspiration. Where a feature is stubbed
> or partial, it says so. Numbers are stated with their assumptions.

---

## 1. What the product is

Simulation Labs points a **swarm of simulation agents at a live website and makes them attempt a
real task** — sign up, check out, cancel — and records the exact pixel where each one gives up.
Every agent is a computer-use agent whose **perception and actuation are mechanically degraded**
(blur, downscale, colour-vision filters, click-coordinate noise, tiny viewports, hard step/time
budgets) so it behaves like a distinct real-world user segment instead of an idealized one. The
output is a **survival curve, an abandonment heatmap on your actual page, video receipts of every
failure, and cloned-voice exit-interviews** where each agent that quit explains why — grounded in
its real action trace, not a vibe.

**One-line pitch:** *Find exactly where your funnel silently loses conversions — with video and
voice receipts, before your real users churn.*

**The category:** behavioral synthetic users. Existing "synthetic user" tools simulate what users
*say* (and are documented to be shallow and people-pleasing). We simulate what users *do*: the
agent either gets through your form or it doesn't. Failure is the product.

---

## 2. Full feature inventory (grounded in the code)

### Core simulation engine — LIVE
- **Behavioral swarm run.** Point at any URL + a plain-English task + a set of personas; each
  persona runs as its own browser session (Playwright) in parallel. (`src/ghostpanel/runner/`,
  `server/swarm.py`)
- **Mechanical perturbation (the real IP).** Perception/actuation are degraded *before* the agent
  sees the screen or *after* it decides a click — not prompt roleplay. Implemented perturbations
  (`engine/perturbation.py`, `personas/*.json`): Gaussian blur, downscale, colour-vision-deficiency
  filter (deuteranopia), click-coordinate noise ("tremor"), small viewport, step-budget +
  wall-clock deadline ("impatience"), literal-reading constraint ("low literacy / non-native").
- **8 shipped personas / behavioral segments** (`personas/`): `power-user` (baseline control),
  `ai-agent` (headless, is-your-site-agent-ready), `grandma-72` (first-timer, blur+tremor+literal),
  `low-vision` (heavy blur+downscale), `colorblind` (deuteranopia), `tremor` (14px click noise),
  `impatient-mobile` (390×844 viewport, 30s deadline, 8-step budget), `non-native` (literal
  reading, impatience). Baseline personas are the control the impaired ones are measured against.

### Reporting & receipts — LIVE
- **Survival curve** — who completed, how far each got before finishing/quitting. (`components/SurvivalCurve.tsx`, `report/builder.py`)
- **Abandonment heatmap** — clustered death points overlaid on a real screenshot of your page. (`components/Heatmap.tsx`, `report/heatmap.py`)
- **Video receipts** — the `.webm` of each session, per persona. (`runner/`, linked in RunDetail)
- **Voice exit-interviews** — each persona that quit explains why in a cloned voice (Gradium TTS/STT),
  grounded in its action trace; narration via Anthropic. (`voice/gradium_voice.py`, `voice/narrate.py`, `voice/voices.py`)
- **Run insights / Simulation Score** — a 0–100 composite completion score, per-run and per-persona
  stats (steps, latency p95, action-type breakdown, "rage-click" repeated-action count,
  median-steps-to-abandon), and an agent-readiness verdict. (`report/insights.py`, `web/src/insights.ts`)
- **Full HTML report** — self-contained `report.html` artifact per run. (`report/html_report.py`)

### Hosted dashboard (product) — LIVE
- **Auth + multi-tenant projects** — signup/login, project switcher, per-project isolation. (`dashboard/pages/Login.tsx`, `Signup.tsx`, `dashboard/auth.tsx`, `server/auth`)
- **Run history + completion trend** — last 50 runs, per-flow filter, completion-across-deploys trend chart. (`pages/Runs.tsx`)
- **Run detail** — headline completion %, per-persona survival, heatmap, video + voice receipts, and
  **"set as baseline for this flow."** (`pages/RunDetail.tsx`)
- **Team / members** — invite by email, remove, roles (owner/member), seat limits enforced. (`pages/Members.tsx`)
- **Billing** — Stripe Checkout + customer portal, live usage meters (runs/period, seats), plan
  entitlements. Degrades gracefully when Stripe isn't configured. (`pages/Billing.tsx`, `billing/`)
- **Settings / API keys** — create/revoke project API keys (hash-stored, shown once) for CI auth. (`pages/Settings.tsx`, `auth/apikeys.py`)

### CI/CD "conversion gate" — LIVE engine, partial UX
- **`sim` CLI + `simulationlabs/gate` GitHub Action** — reads a `sim.yml`, runs the defined flows
  against your deploy from CI, diffs the new run against a stored baseline, and **fails the build if
  completion regresses** past `fail_under`. Exit codes + CI-formatted output. (`cli/main.py`,
  `cli/regression.py`, `cli/ci_output.py`, `cli/exit_codes.py`)
- **Flows authoring page** — generates `sim.yml` (flows, ICP/persona selection, swarm rpm +
  max_personas). **Note: client-side generator only — no backend flow persistence yet**; you copy
  the YAML into your repo. (`pages/Flows.tsx`)
- **Regression engine** — file header marks it a stub with frozen signatures; treat as
  functional-but-hardening. (`cli/regression.py`)

### Competitive / benchmarking — LIVE
- **Before/after compare** — pick two runs, see Simulation Score delta, overlaid survival curves,
  per-persona dead→alive flips, findings-count delta. (`components/CompareView.tsx`)
- **Run index / leaderboard** — every run on the server, worst sites first ("hall of shame");
  measured, not self-declared, agent-readiness. (`components/IndexView.tsx`)

### Governance (stretch, present) — PARTIAL
- **Policy-gated actions** — steps can be routed through a policy gateway and blocked (browse-but-
  never-submit/pay); blocked-action counts surface in insights. (`cli/safety.py`, insights `blocked_actions`)

### Adjacent capability, kept out of customer-facing copy — see §4 note
- The insights layer can map failures to compliance criteria. This is a **latent expansion**, not
  our positioning. We lead with conversion, always.

---

## 3. How customers use it (end-to-end journey)

Onboarding a real customer:

1. **Sign up** at the dashboard, create a **project** (one per site/team). You're on Free by default.
2. **Run your first simulation the fast way.** On the launch screen, paste a **URL** (e.g.
   `yoursite.com/signup` or `/checkout`), type the **task** in plain English ("Create an account and
   reach the verification step"), and **pick your personas** — the behavioral segments you want to
   send (all 8 by default; deselect to focus). Hit **Run simulation**.
3. **Watch it live.** A grid of personas attempts the task in parallel, each tile streaming a
   thumbnail + a human caption ("Clicking Sign up"). Impaired personas visibly stall and freeze red
   at the pixel where they abandon.
4. **Read the survival curve.** Headline number: *"4 of 6 personas completed the task."* See exactly
   how far each got and *how* they died (step budget, time budget, stuck, error).
5. **Read the abandonment heatmap.** The death points cluster on a real screenshot of your page —
   the literal coordinates where your funnel leaks.
6. **Watch the receipts.** Open the `.webm` of any failed session and see the fumble frame-by-frame.
7. **Hear the exit-interview.** Each persona that quit tells you, in voice, why — grounded in what it
   actually did ("I couldn't tell which button submitted the form"), not a hallucinated opinion.
8. **Act, then prove the fix.** Ship a change, re-run, and use **before/after compare** to see the
   Simulation Score move and dead zones disappear.
9. **Make it continuous (the sticky step).** In **Flows**, define your funnels as `sim.yml`, create
   an **API key** in Settings, add the **`simulationlabs/gate`** step to CI, and **set a baseline**.
   Now every deploy is auto-run and the build **fails if conversion regresses** — funnel health
   becomes a CI check, like tests. The **Runs** trend chart tracks completion across deploys.
10. **Grow the account.** Invite teammates (Members), and upgrade in Billing when you hit the run or
    seat quota.

---

## 4. ICP — who to sell to (ranked)

**Positioning rule:** every pitch is CRO — *"you are silently losing conversions and revenue; here
is exactly where, with receipts."* Never "accessibility" or "compliance testing." The impaired
personas are the *mechanism* that surfaces friction real analytics can't localize.

### #1 — Head of Growth / VP Growth / Head of CRO at a PLG SaaS or DTC brand *(primary wedge)*
- **Company:** self-serve SaaS or e-commerce, real paid acquisition, $2M–$50M revenue, a signup or
  checkout funnel that converts below where they want it.
- **Pain:** they pay for traffic, analytics tells them *that* users drop at step 3 but not *why* or
  *at which pixel*; session replay is a needle-in-haystack; a 1pt conversion lift is worth real money.
- **Why us:** we hand them the exact abandonment coordinate + a video + a voice reason, in an hour,
  with no code and no waiting for real-traffic sample size.
- **Buying trigger:** a redesign/launch, a flat or falling conversion rate, a rising CAC.

### #2 — Head of Product / Product-led-growth engineering lead
- **Company:** PLG product with an activation funnel and a real CI/CD pipeline.
- **Pain:** conversion regressions ship silently and are found weeks later in a dashboard.
- **Why us:** the `simulationlabs/gate` CI check turns funnel completion into a build gate. This is
  the **retention/stickiness ICP** — once it's in CI, it doesn't churn.

### #3 — Conversion / CRO / UX-research agencies
- **Company:** agencies running optimization retainers for multiple clients.
- **Pain:** need fast, defensible "here's where it breaks and why" evidence to justify retainers and
  win the next engagement.
- **Why us:** multi-project workspaces + video/voice receipts = a repeatable deliverable across
  clients; we're their tooling layer. Higher runs/mo, multi-seat → best expansion economics.

### #4 (adjacent, do not lead) — Enterprise digital/experience teams
- The **Audit** tier and on-infra (self-host) inference serve teams with data-residency needs and a
  budget for deep, white-glove funnel-forensics engagements. Sell CRO outcomes; residency/governance
  is a closer, not the opener.

---

## 5. Cost model

### Assumptions (stated)
- **A "run"** = 1 flow × ~6 personas × ~30 screenshot→decide steps ≈ **~180 inference calls**;
  each call ≈ ~2k input tokens (screenshot-as-vision + prompt) + ~50 output tokens.
- **Managed API inference** priced at $0.25 / 1M input, $1.80 / 1M output (current open-weights
  35B-MoE vision-action backend). Free tier is 5–10 req/min — a hard concurrency ceiling, so paid
  API or self-host is required for any real swarm.
- **Self-host** = the same open-weights model (Apache-2.0, 3B active params) on one H100
  (~$2/hr on-demand ≈ **~$1,500/mo**, cheaper reserved). Removes the rate limit entirely (bounded
  only by GPU count) and keeps customer data on-infra.
- **Platform floor** (both paths): managed Postgres + object storage base + app hosting for the two
  services + domain ≈ **~$150/mo** at low scale (grows sublinearly).

### Per-run cost (all-in)

| Component | Per-run (managed API) | Per-run (self-host) |
|---|---|---|
| Inference (180 calls) | ~$0.106  (180 × [2k×$0.25/M + 50×$1.80/M]) | ~$0 marginal (GPU is fixed cost) |
| Voice exit-interviews (Gradium TTS + STT, ~4 clips + Q&A) | ~$0.08 | ~$0.08 |
| Narration (Anthropic, short summaries/captions) | ~$0.02 | ~$0.02 |
| Video + audio storage/egress (amortized) | ~$0.02 | ~$0.02 |
| **All-in variable cost / run** | **~$0.22 (budget ~$0.25)** | **~$0.12** |

Inference is *not* the dominant cost once you add voice — the receipts are. Both are trivial vs.
what a conversion point is worth, which is the whole pricing story.

### Monthly infra at three volume scenarios

Variable cost = runs × $0.25 (managed) or × $0.12 (self-host, above the fixed GPU floor).

| Runs / mo | Managed API total | Self-host total | Cheaper path |
|---|---|---|---|
| 10 | $150 floor + $2.50 = **~$153** | $150 + $1,500 GPU + $1.20 = **~$1,651** | **API** |
| 100 | $150 + $25 = **~$175** | $150 + $1,500 + $12 = **~$1,662** | **API** |
| 1,000 | $150 + $250 = **~$400** | $150 + $1,500 + $120 = **~$1,770** | **API** |
| 10,000 (crossover reference) | $150 + $2,500 = **~$2,650** | $150 + $1,500 + $1,200 = **~$2,850**† | ≈ tie |

†One H100 at 10k runs/mo ≈ 1.8M calls/mo ≈ ~0.7 calls/sec — comfortably within a single GPU, so at
this volume the GPU line stays flat while the API line keeps climbing. **Inference-only breakeven**
(ignoring voice, which is common to both) is ~$1,500 ÷ $0.106 ≈ **~14,000 runs/mo**; all-in it lands
around **~10k runs/mo**. Below that, managed API wins on pure cost; adopt self-host earlier only to
kill the rate limit or to satisfy on-infra/data-residency requirements (the Audit tier's real reason).

**Fixed monthly floor to keep the lights on: ~$150/mo** (managed API path, low scale). Self-hosting
adds a **~$1,500/mo** step function you should only take past ~high-thousands of runs/mo or for
enterprise residency deals.

---

## 6. Pricing recommendation

### Headline model (pick this one): **per-seat SaaS with monthly run quotas + a CI gate.**
Not per-run. Runs cost us ~$0.25 and each one can surface a conversion point worth thousands — pricing
per run would anchor buyers to our cost and cap our value capture. Seats + generous run quotas price on
*value and team footprint*, match the entitlements already coded (`billing/entitlements.py`:
Free / Team / Audit), and make the CI gate — the retention hook — the reason to stay. Overage on runs
protects margin at the tail without making metering the headline.

### Recommended tiers (repriced from the placeholder $49/seat in code)

| Tier | Price | Included | Key entitlements | For |
|---|---|---|---|---|
| **Free** | $0 | 1 flow, 50 runs/mo, 1 seat, public URLs, dashboard runs only | PLG land / self-serve trial | Individual PM/growth kicking tires |
| **Team** *(wedge SKU)* | **$299/mo flat** (3 seats + 500 runs/mo incl.; +$79/extra seat; overage $0.50/run) | 10 flows, private sites, **CI gate + GitHub Action**, before/after compare, run history + trend, video + voice receipts | Mid-market growth/CRO team |
| **Scale** | **$999/mo** (10 seats, 3,000 runs/mo; overage $0.35/run) | Unlimited flows, priority throughput (self-host pool = no rate limit), SSO/roles, full API | Larger CRO orgs & agencies |
| **Audit / Enterprise** | **Custom, from ~$25k/yr** | Everything, dedicated/on-infra inference (data stays on your infra), unlimited, white-glove funnel-forensics engagements + one-time deep-dive reports | Enterprise, residency-sensitive, agencies at scale |

### Gross-margin math (variable COGS only; platform floor amortizes to ~$0/tenant at scale)
- **Team $299:** at *typical* ~150 runs/mo → ~$37.50 COGS → **~87% margin**. At the full 500-run
  quota → $125 COGS → **~58% margin**. Overage billed at $0.50 vs ~$0.25 cost → **~50% on every
  marginal run**.
- **Scale $999:** typical ~800 runs → ~$200 COGS → **~80% margin** on API; on the self-host pool
  marginal inference ≈ $0 → **90%+**. Even at the full 3,000-run quota on API ($750) → ~25% floor,
  which the self-host pool erases at that volume.
- **Blended target:** 80–90% gross margin, standard SaaS, with usage overage as the pressure valve.

### Design-partner / white-glove intro offer (first 5–10 logos)
**"Founding Funnel Partners":** 3 months of **Scale-tier access free**, plus one **white-glove funnel
forensics teardown** — *we* run your top funnel across the full persona swarm and hand back the
survival curve, abandonment heatmap, video + voice receipts, and a **prioritized, ranked fix list** —
in exchange for: a logo + testimonial, a co-authored case study (the conversion-point they'd otherwise
never have found), and weekly feedback. Convert to Team/Scale at month 3. This does double duty:
it lands references *and* generates the "we found $X in leaked conversion" proof points every cold
email below needs.

---

## 7. Cold email templates (top ICP: Head of Growth / VP Growth)

Each ≤120 words. Subject + body. Specific, no fake metrics — swap `[bracketed]` for real research.

### Variant A — the pixel
**Subject:** where [Company]'s signup silently loses people

Hi [Name],

You already know [Company]'s signup converts at [X]% — analytics tells you *that* people drop, never
*where* or *why*.

We send a swarm of computer-use agents through your real signup, each one degraded to behave like a
distinct user (rushed-on-mobile, low-vision, first-timer). They either finish or quit at an exact
pixel — and we hand you the video of the fumble plus a voice clip of each one explaining why it gave up.

No code, no tag, no waiting for traffic. First funnel is on us as a founding partner.

Want the teardown of your signup this week?

[You]

### Variant B — the CAC angle
**Subject:** you're paying for traffic that dies at step 3

Hi [Name],

Every abandoned signup at [Company] is CAC you already spent and won't get back.

We reproduce those abandonments on demand: a swarm of agents attempts your real flow under realistic
constraints — a phone in a hurry, a shaky hand, someone who reads every label literally — and freezes
at the exact point each one quits. You get a heatmap of where they die on your actual page, plus video
and voice receipts.

It's the "why" your funnel dashboard can't give you.

15 minutes to run it on [Company]'s checkout live?

[You]

### Variant C — the CI gate
**Subject:** catch conversion regressions before they ship

Hi [Name],

Most funnel regressions ship silently and get spotted weeks later in a dashboard.

We turn funnel completion into a CI check. Define your key flows once; on every deploy a swarm of
realistic agents runs them and the build fails if conversion drops past your threshold — with video +
voice receipts of exactly what broke.

It's like tests, but for whether humans can actually get through your product.

We'll wire it into [Company]'s pipeline free as a founding partner. Worth a look?

[You]

---

## 8. Positioning one-pager

### Headline
**See exactly where your funnel loses people — with receipts, not guesses.**

### Subhead
Simulation Labs sends a swarm of computer-use agents through your real signup, checkout, or activation
flow — each one mechanically constrained to behave like a real-world user — and records the exact pixel
where each one gives up, with video and a voice explanation of why.

### Three proof points
1. **The exact pixel, not a funnel step.** A survival curve + an abandonment heatmap on a real
   screenshot of your page — you see *where* people die, down to the coordinate, not just *which step*.
2. **Receipts, not vibes.** Every failure ships with a `.webm` video of the fumble and a cloned-voice
   exit-interview grounded in the agent's actual actions — evidence you can forward to eng and design.
3. **On demand, in CI, before real users.** No traffic, no tags, no sample-size wait. Run it now, or
   gate every deploy so a conversion regression fails the build like a broken test.

### The honest differentiator
Other "synthetic user" tools ask an AI to *opine* about your UX — and it people-pleases. We don't ask;
we make the agent **attempt the task** with **mechanically degraded perception and actuation** (real
blur, real coordinate noise, real time budgets — not "pretend you're in a hurry"). It either gets
through your form or it doesn't. We don't claim to read minds; we claim **mechanical fidelity**: the
perceptual and motor constraints are genuine, so the failure is genuine. Failure is the product.
