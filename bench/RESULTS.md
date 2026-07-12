# Ghostpanel memory layer — benchmark results

All numbers below are from **live** runs (real Holo API, real Supermemory API) on
2026-07-12, not simulations. Scripts are in `bench/`; raw JSON in `bench/results/`.
Re-run any of them with `.venv/bin/python bench/<name>.py`.

**Hardware/tier caveats:** Holo free tier = **5 requests/minute** shared by the
whole swarm (so wall-clock is rate-limited, not compute-limited). Supermemory on the
free/hosted tier. Small n on the efficacy runs (n=3/condition) — read those as a
pilot, not a powered study; the per-step economics are the robust part.

---

## 1. Token economics (exact, measured)

Per **step**, Holo receives: the degraded screenshot (base64) + the static action
space + up to 10 history captions. Captured from the API's `usage` (image included):

| Quantity | Value |
|---|---|
| Input tokens / step | ~1,530 (step 1) → grows ~15–20/step with history |
| Output tokens / step | ~85–120 |
| **Cost / step** (Holo3-35B-A3B: $0.25/1M in, $1.80/1M out) | **~$0.0006** |
| Cost of a typical 7-step run | ~$0.004 |

The image dominates: text (task + action space + history) is a small minority of the
~1,600 input tokens. **Fewer steps is the only large lever on cost** — you can't
meaningfully shrink a step, only avoid it.

---

## 2. Efficacy — does site-memory make a repeat visit cheaper?

Protocol: run `power-user` against the bundled hostile signup form
(`fixtures/hostile_form.html`) as a first-time visitor (`memory_mode=off`), seed
site memory from the run, wait for ingestion, then run again as a returning visitor
(`memory_mode=site_hints`). n=3 per condition.

| Condition | Success | Mean steps | Mean tokens | Note |
|---|---|---|---|---|
| **off** (baseline) | 67% | 7.33 | 12,273 | first-time visitor |
| **site_hints** (heuristic distill) | 67% | 7.33 | 12,628 (+2.9%) | hints were non-actionable |
| **oracle** (good playbook) | **100%** | 7.0 (−4.5%) | 12,449 (−1.4%) | grounded, actionable hints |

**Findings (honest):**
- The memory **infrastructure works** — recall → task-injection → write → exact-token
  capture all fire correctly end to end.
- **Heuristic distillation of a *successful* run yields useless hints.** It produced
  `"QuantumLeap account … was created"` and `"Alex is a power user"` — outcome facts,
  not navigation guidance — so it gave **zero** step reduction and a small token
  *overhead*. This is the single most important result: **distillation quality is the
  lever, not the memory layer.**
- A **good (oracle) playbook** — "dismiss the cookie wall first; the real button is the
  grey one at the bottom, not the blue decoy; scroll to reveal the promo field" —
  lifted **success 67% → 100%** but barely moved steps/tokens, because power-user was
  already at this form's ~7-step optimum. **On a task the agent nearly solves,
  memory's payoff is reliability (fewer abandonments), not token reduction.**
- **Break-even model:** a carried hint costs ~100 tokens/step (it's re-sent every
  step). A saved step is worth ~1,600 tokens. So memory pays for itself on tokens only
  when the task has **headroom** (≥~1 avoidable step per run). This form gave
  power-user none — but a struggling/impaired persona on a longer flow would.

**Where the token win actually lives:** high-headroom tasks (impaired personas that
wander, multi-page flows) **combined with** actionable failure-derived distillation.
Neither the current heuristic distiller nor an already-optimal persona exercises it.

---

## 3. Memory-layer latency (live Supermemory)

| Operation | p50 | p95 | p99 | mean |
|---|---|---|---|---|
| Recall (`search.memories`, rerank on) | **727 ms** | 1016 ms | 1593 ms | 748 ms |
| Recall (rerank off) | 548 ms | 1508 ms | — | 690 ms |
| Write accept (`documents.add`) | 1451 ms | 2455 ms | 2595 ms | 1613 ms |

- **Rerank costs ~179 ms at p50** — cheap for the relevance it buys; keep it on for recall.
- **Recall (~0.7 s) is fast enough to run once per persona at run start** without
  materially affecting a run gated by 5 RPM Holo calls.
- **Ingestion lag (write → searchable) is erratic:** probes appeared at 0.55 s and
  15.9 s, and **2 of 4 exceeded the 60 s timeout**. There is no reliable SLA. This is
  why the architecture is **cross-run only** (write at run-end, recall at the start of
  a *future* run) and must tolerate not-yet-indexed writes — never write-then-read
  within a run.

## 4. Recall quality (live Supermemory)

- **Precision@3 = 0.75, MRR = 0.75** over 8 labeled queries (6/8 gold hints ranked #1;
  2 missed entirely). Good, not perfect — expect the right hint most of the time.
- **Container isolation: 24/24 checks, 0 leakage.** Per-site/per-persona namespaces
  are genuinely isolated — a strong correctness guarantee for multi-tenant memory.

## 5. Scaling (live Supermemory)

| Store size | Recall p50 | Recall p95 | Needle rank | Needle similarity |
|---|---|---|---|---|
| 25 | 942 ms | 3187 ms | **1** | 0.856 |
| 100 | 819 ms | 1341 ms | **1** | 0.856 |
| 250 | 920 ms | **19285 ms** | **1** | 0.856 |

- **Recall quality does not degrade with size:** the planted needle stayed **rank #1 at
  constant similarity** from 25 → 250 records. The knowledge base scales on relevance.
- **p50 latency is flat (~0.8–0.9 s)** regardless of store size…
- …**but the p95 tail spikes to ~19 s at 250 records** — a few slow calls (likely
  free-tier 429/5xx → SDK auto-retry) dominate the tail. On a paid tier or with a
  client-side concurrency cap this should flatten; worth watching in production.

---

## Bugs found & fixed while benchmarking

1. **Empty `SUPERMEMORY_BASE_URL` footgun** — a blank env var resolves to `""` (not
   `None`), and the SDK only defaults on `None`, so it sent a protocol-less URL
   (`httpx.UnsupportedProtocol`). Fixed: `SupermemoryStore` now always passes an
   explicit base URL. (Would have broken any deployment copying `.env.example`.)
2. **Container tag > 100 chars silently dropped writes** — long hostnames / `file://`
   fixture paths produced tags Supermemory rejects with HTTP 400 `too_big`; the store
   swallows errors, so returning-user writes vanished silently. Fixed: `site_tag` /
   `persona_site_tag` now deterministically cap tags at 100 chars with a hash suffix
   (regression test in `tests/memory/test_tags.py`).

## Recommendations (in priority order)

1. **Upgrade distillation to actionable playbooks.** The biggest ROI is not the memory
   store — it's turning traces into ordered, failure-derived guidance ("dismiss X
   first, the real control is Y, avoid decoy Z"). An LLM distiller over failure traces
   (we already have `ANTHROPIC_API_KEY` wired) would move this from the heuristic floor
   toward the oracle ceiling.
2. **Benchmark on high-headroom tasks/personas** to demonstrate the token win —
   impaired personas on multi-page flows, where the naive agent wanders.
3. **Add a client-side concurrency cap** on Supermemory calls to tame the p95 tail at
   scale; keep recall to one call per persona at run start.
