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
accounts/payments on third-party sites — it's the honest thing to do and it's the NemoClaw
policy-sandbox story (agents can browse but never submit). Some sites have anti-bot/CAPTCHA that can
block any agent; the bundled hostile form is the reliable fallback.

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

## The 90-second demo script (Round 1: 1:30 pitch + 1:30 demo)

**Pitch (say this):**
> "Every synthetic-user research tool asks AI personas what they *think* of your site — and gets
> shallow, people-pleasing answers. Ghostpanel is different: our personas *use* your site. We
> take H Company's Holo computer-use model and **mechanically degrade its perception and
> actuation** — we blur the screenshot for low vision, add coordinate noise for a hand tremor,
> cap patience for the impatient. They either finish your signup or rage-quit at an exact pixel.
> Failure is the product."

**Demo (drive this):**
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

## Sponsor coverage (say the sponsor's name to the sponsor's judge)

- **H Company (6/11 judges):** Holo is the engine. The **AI-agent persona** = "is the web ready
  for *your* agents?" — we use H's model to validate H's own thesis.
- **Gradium challenge:** every exit-interview is Gradium TTS in a per-persona voice; semantic-VAD
  STT can field a live "why did you quit?" question.
- **NVIDIA / NemoClaw challenge:** set `NEMOCLAW_GATEWAY_URL` to route Holo inference through the
  OpenShell policy gateway — a swarm that provably can browse but never submit/pay/exfiltrate.
  (Pull the real YAML policy live from `docs.nvidia.com/nemoclaw/latest/llms.txt` — don't fabricate.)
- **Accel:** the "behavioral synthetic users" category story + EAA/ADA compliance + agent-readiness.

## Known edges (be honest if asked)
- Live report heatmap overlays a reference screenshot; the offline replay's heatmap is the polished
  one — demo the offline report.
- On the free H tier, keep live swarms small; the offline replay is the safety net.
- On-device Nemotron (full local privacy mode) needs an NVIDIA GPU — out of scope for the laptop demo.
