# Ghostpanel — Vision

> **Synthetic users that *do*, not *say*.**
> Hear your users fail — before they're real.

## The problem

There is a whole funded category of "synthetic user research" tools — you interview AI
personas, survey them, run concept tests. They share one documented, fatal flaw: the
answers are **shallow and people-pleasing**. Nielsen Norman Group found synthetic users
claim they "completed all the courses" where real users admit "I finished three of seven,"
and they praise nearly every concept. The deeper, structural critique: **what people *say*
and what people *do* are different things.** Attitudinal AI can approximate the former. It
cannot replicate the latter.

That gap is the whole opportunity. Until computer-use models got good, you *couldn't*
simulate doing. Now you can.

## The product

Ghostpanel points a **swarm of H-Company Holo computer-use agents** at a live website, each
one locked into a persona, each attempting a real task — sign up, check out, cancel. They
don't opine about your checkout flow; they **attempt** it, and either finish or **rage-quit
at a specific pixel**. Failure is the product. The people-pleasing problem *cannot exist*
here: the agent either got through your form or it didn't.

We turn every run into:
- a **survival curve** — who made it, how far each got;
- an **abandonment heatmap** — where, on your actual page, users die;
- **video receipts** — the `.webm` of each failure;
- **voice exit-interviews** — each dead persona explains why it quit, in its own
  **Gradium-cloned voice**, grounded in its real action trace (not vibes — receipts).

## The technical differentiator (why it's simulation, not roleplay)

Anyone can prompt "act like a 70-year-old." We instead **perturb the agent's perception and
actuation channels** to *mechanically* model the impairment, using the fact that Holo is a
screenshot-in / action-out model we fully control:

| Persona trait | Mechanical perturbation |
|---|---|
| Low vision | Gaussian-blur / downscale the screenshot **before** Holo sees it |
| Colour blindness | DaltonLens deuteranopia/protanopia filter on the input frame |
| Motor tremor | Gaussian noise injected into the click coordinate before execution |
| Impatience | Hard step-budget + wall-clock deadline; abandon on no progress |
| Mobile / cracked screen | Tiny viewport + fat-finger coordinate noise |
| Low digital literacy | Prompt constrained to literal reading, no inferred UI conventions |
| **AI agent** | No perturbation — *is your site usable by an agent at all?* |

This is the honest answer to "how do you know it behaves like a real impaired user?" We don't
claim psychological fidelity — we claim **mechanical fidelity**: the perceptual and motor
constraints are real even if the personality is synthetic. That distinction is what earns the
respect of the ML researchers on the panel.

## Why this wins *this* hackathon

Scoring is 5×20 — **Technicality, Creativity, Usefulness, Demo, Sponsor alignment** — so 80%
is not raw tech. Ghostpanel is engineered so **every criterion and both side challenges are
load-bearing**, not decorative:

- **Technicality (20):** perturbing the perception/actuation channels of a VLM is a genuine,
  tunable, measurable trick — not prompt-dressing.
- **Creativity (20):** "behavioral synthetic users" is a category nobody credible is selling.
- **Usefulness (20):** accessibility compliance (ADA suits; EU Accessibility Act, in force
  2025), pre-launch funnel forensics, localization QA — real budgets, not sympathy.
- **Demo (20):** a live grid of 6–8 personas failing in parallel, freezing red at the pixel
  they die on, then a synthetic grandmother explaining in voice why she gave up. That's the clip.
- **Sponsor alignment (20):** Holo is the engine; Gradium is how failure becomes empathy;
  NemoClaw sandboxes a swarm that provably can browse but never purchase/submit.

**The agent-readiness angle** is our alignment ace: as computer-use agents become shoppers and
bookers, every business needs to know *"can an agent even use my site?"* We use H Company's
model to test whether the web is ready for H Company's future — said to a panel that's 6/11 H
Company, that's worth real points.

## Positioning vs. Tester H (say this out loud)

> **Tester H checks whether the software works as specified. Ghostpanel checks whether humans
> survive it.** Functional correctness vs. human experience — upstream, complementary, built
> on H's own models.

## Track & challenges

- **Track 2 — Browser Use** (logins, popups, cookie walls, infinite scroll — literally our demo).
- **Gradium challenge:** cloned per-persona voices, live muttering, semantic-VAD exit-interview Q&A.
- **NVIDIA / NemoClaw challenge:** route Holo inference through OpenShell's policy gateway; a
  live-pulled YAML policy proves the swarm can browse but never submit/pay/exfiltrate.

## Life after the weekend

The afterlife is a company thesis, which is what the VC judge scores: **behavioral synthetic
users** as the missing half of the synthetic-research industry; **accessibility-compliance
evidence** ("here is video of a low-vision user failing your checkout") that beats any static
linter; and an **agent-readiness certification** metric nobody offers yet.
