# Hackathon demo — how to reproduce the money-shot run

Goal: a real run where a **capable agent completes** the signup (functional pass)
but **tremor / imprecise-pointer segments abandon** at the 24px consent checkbox —
the "add a hand tremor and the same agent can't finish" contrast, on video.

## 1. Serve the demo flow
```bash
# from repo root — serves fixtures/ at http://localhost:8137/fixtures/…
python3 -m http.server 8137
```
Target: `http://localhost:8137/fixtures/demo_signup.html`
(A clean, generic SaaS signup — NOT a real brand. Safe to publish. The consent
checkbox is a 24px target; only the box toggles, the label text is inert, so an
imprecise click that lands beside it does nothing — exactly like a real fumble.)

## 2. Run the swarm
```bash
set -a; . ./.env; set +a          # loads HAI_API_KEY (Holo) — or set GEMINI_API_KEY + MODEL_BACKEND=gemini
python -m ghostpanel.cli run --config sim.demo.yml --flow signup --out .demo
```
- **Gemini (hackathon requirement):** `export MODEL_BACKEND=gemini GEMINI_API_KEY=…`
  then run the same command. Same 0-1000 coord grid; the engine handles it.
- Holo free tier is 5 RPM, so a 4-persona run takes ~10-15 min. Fine — you're
  capturing `.webm` receipts, not recording live (never record live at 5 RPM;
  the cursor looks frozen).

## 3. What to verify in `.demo/<run_id>/insights.json`
- `personas_succeeded >= 1` AND `personas_abandoned >= 1` (a **stepped** survival curve).
- `fluent` outcome == `success` (functional baseline: the flow works + the agent is able).
- at least one tremor segment (`misclick-prone` / `mobile-thumb`) == `stuck`/abandoned.
- a populated abandonment heatmap clustered on the checkbox pixel.

If `fluent` fails: the flow reads as broken (the gate would say FUNCTIONAL_FAIL) —
retune (checkbox slightly larger / clearer task) until the capable agent completes.

## 4. Gate demo (the CI closing beat)
Show the merge-blocking verdict on camera — this is the "behavioral tests, like
unit tests" payoff:
```bash
python -m ghostpanel.cli baseline --config sim.demo.yml --flow signup --out .demo   # seed a green baseline
python -m ghostpanel.cli gate     --config sim.demo.yml --flow signup --out .demo   # re-run vs baseline
# prints: gate: BEHAVIORAL REGRESSION — completion 0.50 < last-passing bar 1.00   (exit 1)
```
Two verdicts to show: **FUNCTIONAL FAIL** (break the flow → even fluent can't finish)
and **BEHAVIORAL REGRESSION** (flow works, degraded completion drops). Both block the merge.

## 5. Cut the 1-minute playcast (shot list in hackathon-win-playbook.md §7)
Pre-render from the `.webm` receipts; speed-ramp 6-8×; hold only on the death/zoom
frame with the abandonment pixel coordinates burned in + a "Gemini 2.5 Flash · live"
badge. End card: the one-liner + simulationlabs.dev.
