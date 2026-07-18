# 60-second playcast — second-by-second edit script

The online track is won on 7-day engagement of this video. Its only job: make a
stranger stop scrolling in 3 seconds and feel the failure. Cut from the `.webm`
receipts in your run dir (`.demo/<run_id>/` for Gemini, or the saved Gemini run in
`.sim-deliverable-gemini/`). Everything is speed-ramped — NEVER real-time (a step
is ~5–25s; real-time looks frozen).

**Source clips** (per persona, in the run dir):
- `fluent.webm` — the steady agent completing the flow (your "healthy flow" proof)
- `misclick-prone.webm` — the tremor agent scattering clicks and giving up (the money-shot)
- `page@*.webm` — full-page captures if you need a cleaner frame

**Tools:** any editor (CapCut / Premiere / DaVinci / ScreenStudio). All text is
burned-in overlay; no voiceover required (captions carry it — most people watch muted).

---

## Shot list (0:00 → 1:00)

**0:00–0:03 · THE HOOK — cold open on the give-up frame.**
- Freeze-frame from `misclick-prone.webm` at the moment it rage-clicks the checkbox.
- Big text: **"This user is about to quit. Watch where."**
- No logo, no intro. The failure IS the hook.

**0:03–0:06 · Setup, one line.**
- Cut to the clean signup page (frame 0 of any clip).
- Caption: **"We ran AI agents through a signup — one steady, one with a hand tremor. Same task."**
- Small corner badge (keep it up the whole video): **"Gemini 3.5 Flash · live"** + a step counter.

**0:06–0:16 · The steady agent wins.** (`fluent.webm`, speed-ramp 6–8×)
- Cursor moves cleanly: email → password → ticks the consent box → Create account → **"You're in!"**
- Caption: **"Steady hand: done in 4 steps. ✓"**
- Let the green "You're in!" screen land for ~1s. This establishes the flow WORKS.

**0:16–0:38 · The tremor agent fails.** (`misclick-prone.webm`, speed-ramp 4–6× — this is the star, give it room)
- Cursor jitters. It clears email + password, then reaches the tiny consent checkbox.
- It stabs at the box — **misses**. Stabs again — misses. Rage-clicks. Nothing toggles.
- Caption tracks it: **"Same agent. Add a real hand tremor (σ=24px)."** → **"It can't hit the 24px consent box."**
- Let the misses land — this is the emotional beat. Slow-ramp (2×) the final rage-click.

**0:38–0:46 · THE DEATH — freeze + zoom.**
- Freeze on the last click. Zoom into the checkbox. Crosshair + coordinates burned in:
  **"Gave up here → (x, y)"** (read the real pixel from `insights.json` → `failure_coords`).
- Caption: **"The exact pixel where a real user would quit. On video. Reproducible."**

**0:46–0:54 · The receipts pull-back.**
- Cut to the generated `report.html`: the **abandonment heatmap** glowing on the checkbox,
  and the **survival curve** stepping down.
- Caption: **"Every synthetic-user tool tells you what users SAY. We film what they DO."**

**0:54–1:00 · The gate + CTA.**
- 1.5s of the terminal: `gate: 🛑 FUNCTIONAL FAIL` / `❌ BEHAVIORAL REGRESSION` → **merge blocked (exit 1)**.
- Caption: **"Behavioral tests, like unit tests — on every deploy."**
- End card: **simulationlabs.dev** + **"Built with Gemini 3.5"**.

---

## Captions cheat-sheet (copy-paste, edit the pixel)
1. This user is about to quit. Watch where.
2. Two AI agents, one signup. One steady, one with a hand tremor. Same task.
3. Steady hand: signs up in 4 steps. ✓
4. Same agent + a real tremor (σ=24px) → can't hit the 24px consent box.
5. Gave up at pixel (___, ___). On video. Reproducible run-for-run.
6. Every tool tells you what users SAY. We film what they DO.
7. Behavioral tests, like unit tests — blocks the merge when users can't finish.
8. simulationlabs.dev · Built with Gemini 3.5

## Post copy (X / LinkedIn — native upload, YouTube link in first reply)
> We gave two AI agents the same signup. One steady, one with a simulated hand
> tremor. The steady one finished. The other rage-clicked a 24px "I agree" box and
> gave up — and we caught the exact pixel on video. Built on Gemini 3.5.
>
> This is a behavioral test: it runs on every deploy and blocks the merge when real
> users can't finish. 🧵 / demo 👇

## Getting the numbers for the burn-ins
```bash
# failure pixel + outcomes for the captions:
python -c "import json; r=json.load(open('.demo/<run_id>/../report.json')); [print(x['persona_id'], x['outcome'], x.get('failure_coords')) for x in r['results']]"
```
Pick a run where misclick-prone dies AT the consent checkbox (tremor is a
distribution — run 2–3 times and use the cleanest take; that's representative, not
cherry-picked). fluent + ai-agent completing = your "healthy flow" proof.
