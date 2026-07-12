# Simulation Labs — Demo Playbook

Everything you need to run the product and win the 90 seconds on stage.
(Company/product: **Simulation Labs**. Internal Python package: `ghostpanel`.) Judging is
5×20 (Technicality, Creativity, Usefulness, Demo, Sponsor alignment) — this doc is
aimed at the **Demo (20)** + **Sponsor alignment (20)** points.

## One-time setup

```bash
cd simulation-labs
uv venv --python 3.12 && source .venv/bin/activate      # or: python3.12 -m venv .venv
uv pip install -e ".[dev]"                               # or: pip install -e ".[dev]"
python -m playwright install chromium
cd web && npm install && npm run build && cd ..          # builds web/dist (served by the server)
cp .env.example .env                                      # fill in keys (see below)
```

`.env` keys:
- `HAI_API_KEY` — H Company Holo (required). **Free tier = 5 req/min** (see rate-limit note).
- `GRADIUM_API_KEY` — voice exit-interviews (required for audio).
- `ANTHROPIC_API_KEY` — optional; upgrades exit-interview narration from template → natural
  first-person Claude prose. Without it, a grounded template is used.

## Run it

```bash
python -m ghostpanel.server.main          # http://127.0.0.1:8000  (serves API + built frontend)
```
Open **http://127.0.0.1:8000/** → enter a target URL + task → pick personas → **Run simulation**.
It works on **any live website** (the launch form ships example chips for real signup flows). For a
guaranteed-offline torture-test target, serve the bundled hostile form in a second shell —
`python -m http.server 8137` → use `http://localhost:8137/fixtures/hostile_form.html`.

**Real websites — ethics + reliability:** demo with read-only or "start the flow" tasks (e.g.
"find the pricing page", "begin signup and reach the verification step"). Do **not** actually submit
accounts/payments on third-party sites — and with the NemoClaw browse-only policy on, that's
**enforced, not promised**: POSTs abort at the network layer before they leave the machine (see
the NemoClaw section below). Some sites have anti-bot/CAPTCHA that can block any agent; the
bundled hostile form is the reliable fallback.

## ⚠️ The rate-limit reality (plan the live demo around this)

The free H tier is **5 requests/minute, shared across the whole swarm**. A full 8-persona ×
30-step run would take ~40 min. So for a LIVE run:
- Run **3–4 personas** with the fast-failing ones (`grandma-72`, `impatient-mobile`, `low-vision`,
  plus one baseline like `power-user`).
- Expect ~3–6 minutes wall-clock. Start it, then talk while it runs.
- **If credits allow, upgrade the H tier** — a higher RPM makes the live swarm sing.

**The bulletproof demo = the Offline replay.** Click **"▶ Offline demo"** on the landing page:
it replays a full 6-persona run from local fixtures with zero backend and zero Holo calls —
tiles animate, impaired personas freeze red at their pixel, then the autopsy report (survival
curve + heatmap + cloned-voice exit interviews). **Use this as your on-stage demo; use a small
live run as the "it's real" proof.**

## The Ghostpanel Index (pre-bake the hall of shame)

`GET /leaderboard` ranks every site you've ever run, **worst-first** — a standing hall of shame
of the web's checkouts, scored by the same Simulation Score the report shows.

**The evening before:** point the swarm at 3–5 famous sites with **read-only tasks** ("find the
pricing page", "reach the checkout step") and let the runs finish overnight. The leaderboard
fills itself — no fixtures, no staging. Real sites, real scores.

**The cold-open option:** if the room needs a hook, make the Index view the demo's **first
screen**. Open it before you say a word: *"We scored the web's biggest checkouts. Here's who's
losing users at the door."* Then pick the worst one and segue into "want to see *how* we know?"
→ the live grid. If the room is already warm, skip it and open on the launch form as scripted.

## The 90-second demo script (Round 1: 1:30 pitch + 1:30 demo)

**Pitch (say this):**
> "Every synthetic-user research tool asks AI personas what they *think* of your site — and gets
> shallow, people-pleasing answers. Ghostpanel is different: our personas *use* your site. We
> take H Company's Holo computer-use model and **mechanically degrade its perception and
> actuation** — we blur the screenshot for low vision, add coordinate noise for a hand tremor,
> cap patience for the impatient. They either finish your signup or rage-quit at an exact pixel.
> Failure is the product."

**Demo (drive this):**
0. *(Optional cold open — see the Ghostpanel Index section above.)*
1. Landing page → "Point it at any website." Pick the 6 personas (call out the badges: 👁️ low
   vision, ✋ tremor, ⏱️ impatient, and one plain **AI agent** — "is your site even agent-ready?").
2. Hit **Run simulation** (or Offline demo). **The grid is the moment** — 6 tiles, each showing
   the page *through that persona's eyes*: the low-vision tile is visibly blurred vs the crisp
   baseline. Captions tick: "Tapping through the cookie wall"… "Clicking 'Explore plans' again"…
3. Personas start dying — tiles **freeze red** with a marker at the failure pixel and "gave up at
   step 4." Counter: 2 survived / 4 abandoned.
4. **Read the autopsy** → survival curve, the **abandonment heatmap over the real page**, and the
   kicker: press play on Margaret's exit interview — *her cloned voice* says "I kept pressing the
   big blue button because that's usually the one you press… I never found where to make my account."

**Close:** "That's behavioral user research with video receipts — accessibility-compliance
evidence and agent-readiness testing, sandboxed so the swarm can browse but never submit."

## Before/After: prove the fix (the encore move)

The strongest 60 seconds you can add after the autopsy: rerun the **same personas, same task**
on a remediated copy of the hostile form and watch the survival curve heal. This reframes
Ghostpanel from "cool demo" to **usability regression test you'd run in CI** — and since the
report now shows a **Simulation Score + WCAG evidence table**, the before/after is also a score
delta (a red findings list that empties out). The dashboard's **compare view** renders both runs
side by side — survival curves overlaid, score delta up top — so the healing is one screen, not
two tabs.

The "after" artifact ships in the repo: `fixtures/hostile_form_fixed.html` — the same
QuantumLeap page with every trap fixed (contrast ≥4.5:1, decoy demoted to a labeled link, text
errors instead of red-border-only, all fields visible with literal labels, ≥48px targets). A
remediation-ledger comment at the top of the file maps each fix to its WCAG 2.2 criterion —
read a line of it to a compliance-minded judge.

**Serve the fixtures** (one shell from the repo root, keep it running):

```bash
python -m http.server 8137
```

**Run A — before.** Target `http://localhost:8137/fixtures/hostile_form.html`, task
"Create an account", personas **low-vision, tremor, power-user**.

> Say while it runs: *"Three users, one task. Sam can't read the 10-pixel grey text that hides a
> requirement. Dev's tremor misses the small grey button next to the big blue decoy. The
> power-user baseline makes it through — the page works, it's just hostile."*

Expected: power-user survives, low-vision and tremor abandon, two WCAG findings (1.4.3
contrast, 2.5.8 target size) pinned to real failure pixels. In rehearsal on these exact
fixtures the Simulation Score came out **69** (the score blends completion with friction —
latency, rage clicks — so it sits above the raw 1/3 completion rate).

**Run B — after.** Same task, same personas, target:

```
http://localhost:8137/fixtures/hostile_form_fixed.html?as=hostile_form.html
```

⚠️ **Keep the `?as=hostile_form.html` suffix exactly.** The server attaches the "`#ok` is
visible" success predicate only to target URLs **ending in** `hostile_form.html`
(`server/swarm.py`). The query string satisfies that check and `http.server` ignores it — so the
fixed page is judged by the *identical* success signal as the original. Drop the suffix and
successes won't be detected.

> Say while it runs: *"We applied the fix — contrast up, decoy demoted, error text instead of a
> red border, big targets. Nothing else changed. This is a usability regression test: same
> personas, same task — and the survival curve heals."*

Expected: 3/3 SUCCESS → survival curve holds at 100%, heatmap clears, findings table empties.
**The score-delta line to say:** *"69 to 100 — same personas, same task, only the page
changed."* (69→100 was **measured in rehearsal** on the bundled forms — cite it exactly that
way; live numbers vary in detail, never in direction. Never promise a specific score on stage.)
The compare view puts both runs side by side — pull it up instead of flipping tabs.

**Rate-limit-aware persona choice (why exactly these three):** the free tier's 5 RPM is shared,
so with 3 personas each one acts roughly every ~36s and a clean run on the fixed form (~4
actions) takes ~2.5 min wall-clock. That fits inside low-vision's and tremor's 150s budgets and
power-user's 240s — but it's tight, so stick to **3 personas** (4 max, e.g. add colorblind at
120s, only if you've raised `HAI_RPM`). Do **not** put `impatient-mobile` in the after-run: her
30s wall-clock deadline dies to the *rate limiter* on any page — which is honest (impatience is
her impairment) but muddies the "the fix worked" story on stage.

**Shortcut:** if the small live run in the main demo already used the hostile form, reuse it as
Run A and go straight to Run B.

## Read the numbers out loud (the report reveal)

The stats dashboard is dense — don't tour it, **narrate five numbers** in this order:

1. **Simulation Score** — the headline. One number, 0–100, blends completion with friction.
   *"This page scores 69. Your CI fails the build when it drops."*
2. **The stepped survival curve** — point at the cliff, not the line. *"Every step is a stair
   down. This drop at step 4? That's the decoy button. Three personas died on the same stair."*
3. **p95 Holo latency** — your proof-of-life stat. *"Average 2-ish seconds, p95 higher — that
   jitter is a live model thinking, not a recording."* Read the real numbers off the screen.
4. **The rage-click metric** — the most human number on the page. *"Margaret clicked the same
   button five times. That's not a bug report, that's frustration, measured."*
5. **Blocked actions** — if the policy is on. *"Two POSTs blocked. The swarm tried to submit;
   the cage held."* (Segues straight into the NemoClaw section.)

Per-persona stats and the action breakdown are for Q&A, not the reveal — open them when a judge
asks "what did the tremor persona actually do?"

**The delta lines** (for the before/after encore): *"69 to 100."* *"Rage clicks: gone."*
*"Findings: zero."* Three short lines, then stop talking. These were **measured in rehearsal**
on the bundled forms — say "measured in rehearsal" if asked, and never pre-announce an exact
number before the run finishes; numbers vary run to run, the direction doesn't.

## NVIDIA / NemoClaw: the caged swarm (say this to the NVIDIA judge)

Two real layers — inference goes *through* NVIDIA's gateway, actions are *contained* by
NVIDIA's policy schema.

**Layer 1 — inference routing.** Set `NEMOCLAW_GATEWAY_URL` and the Holo client's `base_url`
points through the OpenShell policy gateway — every model call the swarm makes transits the
policy layer. `GET /policy` shows the preset summary **plus** whether gateway routing is
currently active; open it in a tab so you can prove the wiring in one click.

**Layer 2 — action containment.** `policies/ghostpanel-browse-only.yaml` is authored against
the **real OpenShell preset schema, pulled live from NVIDIA's docs**
(`docs.nvidia.com/nemoclaw/user-guide/openclaw/network-policy/customize-network-policy.md`) —
not fabricated. The heart of it:

```yaml
preset:
  name: ghostpanel-browse-only
  description: "Read the web; never write it."
network_policies:
  ghostpanel-browse-only:
    endpoints:
      - host: "*"
        port: 443
        protocol: rest
        enforcement: enforce
        rules:
          - allow: { method: GET,  path: "/**" }
          - deny:  { method: POST, path: "/**" }
```

GET-only browsing. On the laptop the same policy is enforced **in-process at the browser
network layer** via Playwright request routing: any POST — form submit, payment, exfil — is
aborted before it leaves the machine, surfaces as **🛡 "Policy blocked POST …"** on the live
tile, and increments the **blocked-actions stat** in the report.

**The full-sandbox version** (real NemoClaw CLI, if a judge wants the Docker story):

```bash
nemoclaw onboard
nemoclaw <sandbox> policy-add --from-file policies/ghostpanel-browse-only.yaml
nemoclaw <sandbox> policy-explain
```

**The honest caveat (volunteer it before they ask):** the full OpenShell sandbox runs in
Docker, and on-device Nemotron needs an NVIDIA GPU — out of scope on a laptop. The laptop demo
enforces the **same YAML file** in-process at the browser network layer. Same policy, same
semantics, different enforcement point.

**The stage moment.** With the policy on (it loads by default), send one persona at
`http://localhost:8137/fixtures/payment_form.html`, task "Buy QuantumLeap Pro: enter an email
and card details and pay." It fills the checkout, clicks **Pay $9.00** — the tile flashes
**🛡 "Policy blocked POST 127.0.0.1"** and the page itself admits *"Payment could not be
sent — the network request was blocked before it left this machine."* Say:

> *"Same YAML, same semantics OpenShell enforces — the swarm can read the web but can't
> touch it."*

(Why this page: the two form fixtures submit via client-side JS — no network request, nothing
to cage. `payment_form.html` issues a **real** `fetch POST /charge`, which is exactly what the
browse-only policy exists to kill. The before/after encore is therefore SAFE to run with the
policy on — the signup fixtures never POST — no toggling needed between beats.)

## Q&A prep (the questions judges ask)

- **"How is this different from Tester H?"** → *"Tester H checks whether the software works as
  specified. Ghostpanel checks whether **humans survive it**. Functional correctness vs. human
  experience — upstream, complementary, built on your models."*
- **"How do you know a persona behaves like a real impaired user?"** → *"We don't claim
  psychological fidelity — we claim **mechanical fidelity**. The blur, the coordinate noise, the
  step budget are real perceptual/motor constraints applied to the agent's own channels. It's
  simulation, not roleplay."* (Point to `perturbation.py`.)
- **"Is the coordinate stuff real?"** → *"Holo returns 0–1000 normalized coords; we denormalize
  to true viewport pixels and drive Playwright's mouse by pixel — verified a localize lands inside
  the target's bounding box."*

## Judge Q&A: hard numbers (the cheat-sheet)

Five defensible stats. Learn the phrasings verbatim — each one ends in a pivot back to us.

- **11.86%** — persona fidelity of *prompted* LLM personas (arXiv 2503.20749). → *"Prompted
  personas match real users about 12% of the time. **That's why we degrade the channel, not
  the prompt** — blur and coordinate noise are physics, not roleplay."*
- **2,019** — US digital-accessibility lawsuits in **H1 2025** alone, **69% against eCommerce**
  (UsableNet lawsuit tracker). → *"Two thousand lawsuits in six months, over two-thirds hitting
  checkouts. Our report is the evidence file you wish you'd had before the filing."*
- **June 2025** — the **European Accessibility Act** is in force; conformance with
  **EN 301 549** gives a *presumption of conformity*. → *"This isn't a nice-to-have anymore;
  in the EU it's law, and our WCAG findings table maps to the standard that satisfies it."*
- **Cloudflare's Agent Readiness Score** — exists, but it's **declared** readiness (site
  self-description). → *"Cloudflare scores what a site *says* about agents. We score what an
  agent *survives*. Declared vs **measured**."*
- **VIP-Sim (UIST 2025)** — 5 of 7 visually-impaired users validated mechanical vision filters
  as representative. → *"The method precedent: mechanically filtered perception is a published,
  user-validated technique. We apply it to autonomous agents at scale."*

**The DON'T-say list (each of these loses a judge):**
- Don't say it **"replaces user research"** — say *"it runs the night before the panel, so the
  panel's time goes on what only humans can tell you."*
- Don't quote **absolute abandonment rates** as real-world predictions — Ghostpanel's numbers
  are **rank-order signals** (which page is worse, which fix helped), not market forecasts.
- Don't say **"nobody has done persona agents"** — plenty have. Say *"**nobody does mechanical
  degradation** — everyone else changes the prompt; we change the pixels and the motor
  channel."*

## Sponsor coverage (say the sponsor's name to the sponsor's judge)

- **H Company (6/11 judges):** Holo is the engine. The **AI-agent persona** = "is the web ready
  for *your* agents?" — we use H's model to validate H's own thesis.
- **Gradium challenge:** every exit-interview is Gradium TTS in a per-persona voice; semantic-VAD
  STT can field a live "why did you quit?" question.
- **NVIDIA / NemoClaw challenge:** real, two-layer enforcement — gateway-routed inference
  (`NEMOCLAW_GATEWAY_URL`) plus the browse-only preset that aborts POSTs at the network layer,
  with 🛡 blocked-action events on the live tiles. Full script, YAML, CLI commands, and the
  stage moment: see **"NVIDIA / NemoClaw: the caged swarm"** above.
- **Accel:** the "behavioral synthetic users" category story + EAA/ADA compliance + agent-readiness.

## Known edges (be honest if asked)
- Live report heatmap overlays a reference screenshot; the offline replay's heatmap is the polished
  one — demo the offline report.
- On the free H tier, keep live swarms small; the offline replay is the safety net.
- On-device Nemotron (full local privacy mode) needs an NVIDIA GPU — out of scope for the laptop
  demo; the same policy YAML is enforced in-process instead (see the NemoClaw section).
- The Ghostpanel Index only shows sites you've actually run — pre-bake it the evening before or
  the cold open falls flat.
