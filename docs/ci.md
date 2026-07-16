# The CI gate

Simulation Labs is a **behavioral test suite for your real flows** — it tests what users
*do*, not what they *say*. On every pull request it points a small swarm of behavioral
personas (impatient-mobile, low-vision, tremor, colorblind, non-native, and more) at a live
flow, has each one actually attempt the task (sign up, check out, cancel), and records where
it completes or abandons. Wire it into CI and the check **fails the moment completion
regresses** — the same way a unit test fails when logic breaks.

There is no backend. The gate runs on **your own H Company Holo API key**, in your own CI
runner. Your traffic never leaves your pipeline.

---

## What the gate does

- Runs the behavioral swarm against a real flow (a URL + a goal) on every PR.
- Computes a **completion rate**: the fraction of personas that finished the task
  (`success`). Infra failures (`error`) are excluded from the denominator.
- Compares that against a bar — either an absolute number or the **last-passing baseline**.
- Exits non-zero (`GATE_FAILED = 1`) when completion drops below the bar, which blocks the
  merge. Every other failure mode gets a *different* exit code so a real regression is never
  confused with a broken pipeline.
- Writes a per-persona survival table, a `$GITHUB_STEP_SUMMARY`, a PR comment, and a JUnit
  report.

---

## Local quickstart

```bash
# Until we publish on PyPI, install from git (pipx also works):
pip install "git+https://github.com/SatyamDave/simulation-labs@main"
# pipx install "git+https://github.com/SatyamDave/simulation-labs@main"

# Playwright needs a browser once:
playwright install chromium

# Bring your own H Company Holo key — the whole thing runs on it, no backend:
export HAI_API_KEY=hai-...

# Scaffold sim.yml + .github/workflows/simulate.yml (never clobbers existing files):
sim init

# Run one flow and print the survival table:
sim run --url https://staging.example.com/signup \
        --task "Create an account with a work email and reach the dashboard"

# Seed the first green run as the baseline the gate compares against:
sim baseline

# Gate: re-run, compare to the baseline, block on regression:
sim gate --fail-under last-passing
```

`sim gate` exits `1` when completion drops below the last-passing run. Use that exit code as
the merge signal in CI.

### The `sim` subcommands

| Command | What it does |
|---------|--------------|
| `sim init` | Write `sim.yml` and `.github/workflows/simulate.yml` if absent (never overwrites). |
| `sim run` | Run a flow, write `<out>/report.json`, print the survival table. |
| `sim baseline` | Run (or `--from report.json`) and save the result as `<out>/baseline.json`. |
| `sim gate` | Run (or `--from report.json`), compare vs. baseline/threshold, write CI outputs, **exit `1` on failure**. |

Common flags: `--url`, `--task`, `--personas a,b,c`, `--config sim.yml`, `--out .sim`,
`--fixture PATH` (run against a local HTML file), `--rpm N`. `sim gate` adds
`--fail-under last-passing|<float>`, `--baseline .sim/baseline.json`, `--margin 0.05`.

---

## The `sim.yml` schema

`sim init` writes a starter file. Fields (exact names — validation rejects unknown keys):

```yaml
# sim.yml — Simulation Labs behavioral test.
version: 1

# Each flow is one behavioral test: a real goal on a real page.
flows:
  - name: signup
    url: https://staging.example.com/signup
    task: "Create an account with a work email and reach the dashboard"
    # "last-passing" blocks the merge if completion drops below the last green run.
    # Or set an absolute bar, e.g. 0.8 (80% of personas must finish).
    fail_under: last-passing
    # Optional: override which segments this flow sends (else uses icp.personas).
    personas: [impatient-mobile, low-vision, tremor]

# Which behavioral segments to send across all flows. "auto" = the full bundled roster.
icp:
  personas: auto

swarm:
  rpm: 5           # shared Holo rate limit (free tier ~5 RPM)
  max_personas: 6  # keep the swarm inside the RPM budget

output:
  dir: .sim

safety:
  allow_private: false   # refuse localhost/private targets unless you opt in
  allowlist: []          # when non-empty, ONLY these hosts are allowed
```

| Section | Field | Type | Meaning |
|---------|-------|------|---------|
| `flows[]` | `name` | string | Flow identifier (default `"default"`). |
| | `url` | string | The page the swarm starts on. |
| | `task` | string | The goal, in plain English. |
| | `fail_under` | number `0..1` \| `"last-passing"` | The bar. A number is an absolute completion floor; `"last-passing"` regresses against the baseline. |
| | `personas` | list \| omitted | Optional per-flow segment override; falls back to `icp.personas`. |
| `icp` | `personas` | list \| `"auto"` | Behavioral segments to send. `"auto"` = the full bundled roster. |
| `swarm` | `rpm` | int | Shared Holo rate limit for the whole swarm (default `5`). |
| | `max_personas` | int | Hard cap on swarm size (default `6`). |
| `output` | `dir` | string | Where reports/artifacts land (default `.sim`). |
| `safety` | `allow_private` | bool | Allow loopback/private/`file://` targets (default `false`). |
| | `allowlist` | list | When non-empty, only these hosts (exact or suffix match) are allowed. |

The bundled behavioral segments include `impatient-mobile` (Priya), `low-vision` (Sam),
`tremor` (Dev), `colorblind` (Jordan, deuteranopia), `grandma-72` (Margaret), `non-native`,
`power-user`, and `ai-agent`. Each is a real impairment modeled *mechanically* (blur,
coordinate noise, tight step/time budgets, color-vision filters) so it fails the way that
segment of your users fails.

---

## Exit codes

The CI check keys on these. Only `1` means "the flow regressed"; everything else is a
distinct code so a broken pipeline is never mistaken for a behavioral failure.

| Code | Name | Meaning |
|------|------|---------|
| `0` | `OK` | Gate passed (or a non-gate command succeeded). |
| `1` | `GATE_FAILED` | Completion regressed vs. baseline, or fell below the threshold. **The merge-block signal.** |
| `2` | `CONFIG_ERROR` | Bad/missing `sim.yml`, unknown flow, or invalid arguments. |
| `3` | `RUN_ERROR` | The swarm itself crashed (browser/Holo/infra) — no verdict was produced. |
| `4` | `UNSAFE_URL` | Target rejected by the SSRF guard (see safety below). |

---

## GitHub Actions setup

1. Add your Holo key as a repository secret named `HAI_API_KEY`
   (**Settings → Secrets and variables → Actions → New repository secret**).
2. Commit a `sim.yml` (from `sim init`).
3. Add `.github/workflows/simulate.yml`:

```yaml
# .github/workflows/simulate.yml
name: behavioral gate
on: [pull_request]

jobs:
  simulate:
    runs-on: ubuntu-latest
    steps:
      # behavioral tests for every deploy
      - uses: simulationlabs/gate@v1
        with:
          flow: checkout
          icp: your-segments
          fail-under: last-passing   # block the merge if completion drops
          hai-api-key: ${{ secrets.HAI_API_KEY }}
```

On each PR the check runs the swarm, appends a survival table to the **job summary**, and
posts a **PR comment** with the per-persona breakdown and the verdict (which personas
regressed, and any new abandonment "dead zones" that weren't in the baseline). When
completion drops below the last-passing run the step exits `1` and the required check fails,
blocking the merge until the regression is fixed or the baseline is intentionally re-seeded.

---

## The RPM reality — depth over breadth

The free Holo tier is about **5 requests per minute**, and the whole swarm shares that one
budget (`swarm.rpm`). So keep swarms **small — six personas or fewer** (`max_personas`
defaults to `6`), and expect runs to be *paced*, not instantaneous: a persona takes many Holo
calls to complete a flow, and those calls queue behind the shared limiter.

This is deliberate. The gate is **depth over breadth** — a handful of carefully modeled
behavioral segments driven all the way through your real flow, not a hundred-persona storm
that tells you nothing. Pick the segments that represent your ICP and let them run.

---

## Safety (SSRF guard)

Targets must be **public `https://`** by default. The gate refuses non-HTTP(S) schemes and
loopback / private / link-local / reserved IPs so a workflow can't be tricked into reaching
your internal network.

To test against localhost or a private staging box, opt in explicitly:

```yaml
safety:
  allow_private: true
  allowlist: [staging.internal, 10.0.0.5]   # when set, ONLY these hosts are allowed
```

`allow_private: true` is also what lets `--fixture` run against a local `file://` HTML page.
Leave it `false` in CI unless you genuinely mean to reach a private target.
