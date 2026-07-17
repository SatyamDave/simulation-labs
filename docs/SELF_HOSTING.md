# Self-hosting Holo inference

Ghostpanel's single biggest launch blocker was the **hosted H-Company Holo API's
shared rate limit** (5–10 requests/min on the free tier, shared across the whole
swarm) plus the hard dependency on that external vendor. Every persona step is one
inference call, so a swarm of N personas × M steps is throttled to a crawl and can
never scale.

This document explains how to run the **same Holo weights on your own GPU** behind
an OpenAI-compatible server, point the app at it, and prove the swap is safe with
the **grounding eval gate** before it ships.

Because the Holo endpoint is already OpenAI-compatible **and a self-hosted vLLM
server emits coordinates on the same 0–1000 normalized grid**, the existing
`LiveHoloClient` works against a self-hosted endpoint *unchanged*. Self-hosting is
therefore a config change, not a code change.

---

## 1. Why this works with zero client changes

- The hosted Holo API is OpenAI-compatible; `LiveHoloClient` talks to it through
  the `openai` SDK with a `base_url` swap.
- The hosted Holo3.1 API returns click coordinates **normalized to a 0–1000 grid**,
  and `LiveHoloClient` denormalizes them to true viewport pixels
  (`x/1000*w`, `y/1000*h`). A self-hosted vLLM server running the **same weights**
  (`Hcompany/Holo-3.1-35B-A3B`) produces coordinates on the **same grid**, so the
  same denormalization path is correct — no client change needed.

There are two supported ways to select self-hosted inference:

1. **`MODEL_BACKEND=holo` + `HAI_BASE_URL` pointed at your vLLM `/v1`.** The
   existing `holo` backend already reads `HAI_BASE_URL`, so this works today.
2. **`MODEL_BACKEND=selfhost`** — an explicit backend
   (`ghostpanel.engine.selfhost_client.SelfHostedHoloClient`, a thin subclass of
   `LiveHoloClient`) that makes intent obvious, defaults to a local endpoint, and
   **disables the RPM cap** (self-host has no vendor limit; throughput is bounded
   by your GPU). This is the recommended way.

Both go through the pluggable model registry
(`ghostpanel.engine.models.build_model`); the runner/worker never construct a
client directly.

---

## 2. Stand up the model server

Hardware: a single **NVIDIA H100 (80GB)** at roughly **$2/hr** on most clouds.
Holo-3.1-35B-A3B is a Mixture-of-Experts model: **35B total params but only ~3B
active** per token (the "A3B"), so it is **cheap to serve** — high throughput on
one GPU. In **FP8** the weights fit an H100 with room for KV cache. For smaller
boxes, a **Q4 GGUF** build fits in roughly **12GB** of VRAM (lower throughput).

### Option A — Docker Compose (recommended)

```bash
# Requires the NVIDIA Container Toolkit on the host.
HF_TOKEN=hf_xxx docker compose -f deploy/vllm/docker-compose.yml up -d

# Readiness (first boot downloads tens of GB of weights — be patient):
curl http://localhost:8000/v1/models
```

### Option B — raw `vllm serve`

```bash
pip install "vllm>=0.6.6"
export HF_TOKEN=hf_xxx

vllm serve Hcompany/Holo-3.1-35B-A3B \
  --served-model-name Hcompany/Holo-3.1-35B-A3B \
  --quantization fp8 \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.92 \
  --limit-mm-per-prompt image=5 \
  --trust-remote-code \
  --host 0.0.0.0 --port 8000
```

This exposes the OpenAI-compatible API at `http://<host>:8000/v1`. `--served-model-name`
pins the model id so it matches `HAI_MODEL` regardless of the on-disk path.
`--limit-mm-per-prompt image=5` matches the hosted Holo cap of 5 images/request.

The Dockerfile and compose file live in `deploy/vllm/`.

---

## 3. Point the app at your server

Set these in the app's environment (`.env` or your deploy secrets):

```bash
MODEL_BACKEND=selfhost                       # use the self-host backend
HAI_BASE_URL=http://<vllm-host>:8000/v1      # your vLLM /v1 endpoint
HAI_MODEL=Hcompany/Holo-3.1-35B-A3B          # must match --served-model-name
HAI_RPM=1000000                              # no vendor cap; effectively disabled
HAI_API_KEY=                                 # leave empty unless vLLM has --api-key
```

Notes:
- `MODEL_BACKEND` is read by `ghostpanel.engine.models.default_backend()`.
- If you instead keep `MODEL_BACKEND=holo`, just set `HAI_BASE_URL` to your vLLM
  endpoint — the existing `holo` backend already honours it. The `selfhost`
  backend additionally removes the shared rate limiter.
- If you start vLLM with `--api-key sk-...`, set the same value in `HAI_API_KEY`.
- **Integration note:** wiring the backend into the running server is done via
  these env vars only — no source change to the server composition root is
  required. The registry (`build_model`) already resolves `selfhost`.

---

## 4. Run the grounding eval gate (do this BEFORE every model swap)

Any time you change the inference backend — hosted → self-hosted, a new vLLM
version, different weights or quantization — **re-measure click-localization
accuracy first**. That skill (put the click on the right pixel) is the entire
product; a silent regression there is invisible until users see bad runs.

The gate lives at `tests/engine/grounding_eval.py`. It scores any `HoloClient` on
`(screenshot, instruction, expected_pixel, tolerance)` cases and reports
**click accuracy = % of clicks within tolerance**.

**Offline smoke (CI, no network):**

```bash
pytest tests/engine/test_grounding_eval.py -q
```

**Live gate against your self-hosted endpoint:**

```bash
GROUNDING_EVAL_BACKEND=selfhost \
HAI_BASE_URL=http://<vllm-host>:8000/v1 \
HAI_MODEL=Hcompany/Holo-3.1-35B-A3B \
python -m tests.engine.grounding_eval --min-accuracy 0.5
```

**Live gate against the hosted vendor (baseline to compare against):**

```bash
HAI_API_KEY=sk-... python -m tests.engine.grounding_eval
```

The script prints per-case results and the overall accuracy, and **exits non-zero
if accuracy is below `--min-accuracy`** (default 0.5) so it can be a CI/deploy
gate. If no credentials are configured it skips gracefully (exit 0).

### Interpreting the score

- **accuracy** — fraction of cases whose predicted click landed within the case's
  pixel tolerance. This is the number that gates a swap.
- **mean_distance** — average pixel error across scored cases; a leading indicator
  that quality is drifting even while accuracy still passes.
- **Rule of thumb:** the self-hosted score should **match the hosted baseline**
  (run both, compare). A drop of more than a few points means the swap is not safe
  — check quantization (FP8 vs the reference), `--served-model-name`, image size
  handling, and that coordinates are still on the 0–1000 grid.
- The seed suite is intentionally small (two deterministic synthetic buttons + the
  repo fixture). **Grow it with real target screenshots** before relying on the
  gate for production sign-off.

---

## 5. What changed in the codebase

- `src/ghostpanel/engine/selfhost_client.py` — `SelfHostedHoloClient`, a thin
  subclass of `LiveHoloClient` with self-host defaults and no RPM cap. Reuses all
  parsing/denormalization; satisfies the `HoloClient` Protocol.
- `src/ghostpanel/engine/models/registry.py` — registers the `selfhost` backend.
- `tests/engine/grounding_eval.py` + `tests/engine/test_grounding_eval.py` — the
  eval harness and its offline/live tests.
- `deploy/vllm/` — Dockerfile + docker-compose for the vLLM server.

No changes were made to the server composition root, contracts, or `pyproject.toml`.
