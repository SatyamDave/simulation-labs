# Testing & coverage

How to run the test suites locally, the philosophy behind them, and the coverage
floors CI enforces.

## Running the backend (Python) suite

```bash
python3.11 -m venv .venv && . .venv/bin/activate   # once
pip install -e ".[dev]"                            # includes pytest-cov
playwright install chromium                         # runner/server tests only

# fast run
pytest -q

# with coverage (what CI runs)
pytest --cov=ghostpanel --cov-report=term-missing --cov-fail-under=73 -q
```

- `pytest --cov=ghostpanel` measures line coverage over `src/ghostpanel`.
- `--cov-report=term-missing` prints the uncovered line ranges per file so you
  can see exactly what a new test needs to hit.
- `--cov-fail-under=73` is the CI gate — the run exits non-zero below 73%.
- Contracts must always stay green: `pytest tests/test_contracts.py -q`.

## Running the web (Vitest) suite

```bash
cd web
npm ci                       # or `npm install`

# fast run
npm test                     # == vitest run

# with coverage (what CI runs)
npx vitest run --coverage
```

Coverage uses the V8 provider (`@vitest/coverage-v8`, a dev dependency). Config
lives in `web/vitest.config.ts` under `test.coverage`:

- `all: true` measures **every** source file under `src/`, not only the ones a
  test happens to import — so untested pages count against the total and the
  floor can't be gamed by narrowing the import graph.
- Reporters: `text` (readable CI log) + `json-summary`
  (`web/coverage/coverage-summary.json`, machine-readable for dashboards).
- Thresholds fail the run when coverage drops below the floors below.

## Testing philosophy

- **Contracts are frozen.** `shared/ghostpanel_contracts/` and its test
  (`tests/test_contracts.py`) are the cross-module API. Every module tests that
  its concrete class satisfies its `@runtime_checkable` Protocol via `isinstance`.
  Never edit the contracts to make a test pass.
- **Offline determinism.** Tests must not hit the live Holo / Gradium / Stripe
  APIs or the network. Use the fakes (`FakeHoloClient`, `CollectingEventSink`,
  fixtures under `fixtures/`) so the suite is deterministic and runs in CI with
  no keys. Anything requiring a real browser uses headless Playwright Chromium.
- **Adversarial verification.** A green unit test is necessary, not sufficient.
  Coverage gates ensure new code arrives with tests; term-missing output shows
  what's still unexercised. Prefer tests that assert behavior at module
  boundaries (contract models in, contract models out) over implementation
  details, and probe failure/abandonment paths, not just the happy path.
- **Every step is observable.** Runner/server tests assert that a `StepEvent`
  (thumbnail + caption) is emitted on every step — the live grid depends on it.

## Coverage floors & rationale

Floors are set **just under** the coverage measured on 2026-07 so the gate is
green today, then acts as a ratchet: coverage can rise but a regression below the
floor fails CI. Raise the floors as the suites grow — never lower them to make a
red build pass.

| Suite | Metric | Measured (2026-07) | CI floor |
|-------|--------|--------------------|----------|
| Backend (`ghostpanel`) | lines | 78% (77.63%) | **73** |
| Web (`web/src`) | statements | 2.79% | **2** |
| Web | lines | 2.79% | **2** |
| Web | functions | 27.53% | **25** |
| Web | branches | 53.68% | **50** |

**Why the backend floor is 73 (not 78):** a ~5-point cushion below the measured
total absorbs normal churn (a refactor that removes a well-covered file, a new
lightly-tested module) without a nuisance red build, while still catching a real
coverage collapse. Well-covered layers (store models 100%, metrics 97%, policy
97%) pull the average up; thinner spots are `s3.py` (30%), `voices.py` (8%), and
CLI/entrypoint glue.

**Why the web floors are low:** the dashboard test suite currently covers the
auth flow, `api2` client, and `RequireAuth`; the many page components
(`Runs`, `RunDetail`, `Billing`, `Settings`, …) and the `sim/simulate.ts` engine
are not yet unit-tested, which drags the line/statement total to ~2.8%. The
floors are deliberately set just under each measured metric so the gate is honest
about where we are rather than aspirational — branches (50) and functions (25)
are meaningfully higher because the tested modules are branch-dense. As page
tests land, ratchet these up (the near-term target is lines ≥ 10, then 25+).
