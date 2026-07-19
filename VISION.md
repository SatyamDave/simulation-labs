# Simulation Labs — Vision

> **Simulate exactly how real people behave on your site — before they're real.**
> Synthetic users that *do*, not *say*.

## The problem

There is a whole funded category of "synthetic user research" — you interview AI personas,
survey them, run concept tests. It shares one structural, fatal flaw: **what people *say* and
what people *do* are different things.** Attitudinal AI approximates the former. It cannot
replicate the latter. Synthetic users claim they "finished all seven courses" where a real
user quietly abandons at step three — and they praise nearly every design you show them.

Meanwhile the thing that actually costs you money is never in the survey: the rushed user who
bounces after four seconds, the person on a cracked phone who can't hit your consent checkbox,
the distracted shopper who loses the thread at your third form field. They don't fill out
feedback. They just leave — and your funnel numbers drop with no note attached.

Until computer-use models got good, you *couldn't* simulate the doing. Now you can.

## The product

Simulation Labs points a **swarm of computer-use agents** at a live flow — sign up, check out,
cancel — each one attempting the real task the way a real segment of your traffic would. They
don't opine about your checkout; they **attempt** it, and either finish or **abandon at a
specific, reproducible pixel**. Failure is the product. The people-pleasing problem *cannot
exist* here: the agent got through your form, or it didn't.

It runs as a **behavioral CI gate**. Wire it into your pipeline and every deploy is tested
against a real flow — the build passes when completion holds and **fails when your users start
abandoning**, before the regression ever ships. Unit tests prove the code runs; Simulation Labs
proves a human can finish.

Every run produces:
- a **completion rate** and **survival curve** — who made it, and how far each got;
- an **abandonment heatmap** over your actual page — where, to the pixel, people give up;
- **video receipts** — the recording of each session;
- **exit-interviews** — each agent that quit explains why, grounded in its real action trace.

## Why it's simulation, not roleplay

Anyone can prompt "act like someone in a hurry." We instead **mechanically shape the agent's
perception and actuation** — because the agent is screenshot-in, action-out and we own that
loop. We reproduce the real-world conditions under which people actually use software:

| Behavioral segment | What we mechanically change | The real user it models |
|---|---|---|
| **Fluent** (control) | nothing | the ideal path — your ceiling |
| **AI agent** (control) | nothing | an autonomous agent filling your form |
| **First-timer** | prompt constrained to literal reading, no inferred UI conventions | new to your product, takes nothing for granted |
| **Rushed** | tight step + time budget | bounces if the flow drags |
| **Mobile-thumb** | small phone viewport + fat-finger coordinate noise | on a phone, imprecise taps |
| **Misclick-prone** | coordinate noise on every click | fumbles small controls and gives up |

We don't claim psychological fidelity — we claim **mechanical fidelity**: the perceptual and
motor constraints are real even if the personality is synthetic. The controls set the ceiling;
the degraded agents show you how far below it your real traffic sits, and *where* they walk
away. That's a measurable, tunable signal — not prompt-dressing.

## Where this goes

Behavioral synthetic users are the missing half of the user-research industry: not what a
persona *says* about your design, but whether a realistic slice of humanity can actually get
through it. Three things compound from there:

- **A gate every team runs on every deploy** — the behavioral equivalent of a test suite,
  catching conversion regressions before they reach production.
- **A cross-run model of where real segments give up** — each run sharpens the next, until the
  gate predicts abandonment before the flow even ships.
- **Agent-readiness as its own metric** — as computer-use agents become shoppers and bookers,
  every business will need to answer *"can an agent even use my site?"* We already measure it.

## The company

Simulation Labs is behavioral user research that **does**, not **says**. Open-source core, runs
on your own model key, drops into any CI in one command.

**Want to run it on your funnel, or work with us?** Open an issue, or reach the founder at
**satyam@agentmade.ai**.
