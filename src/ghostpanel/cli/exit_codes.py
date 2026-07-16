"""Process exit codes for the `sim` CLI. FROZEN — see PHASE1_SPEC.md.

CI keys on these: `GATE_FAILED` (1) is the "block the merge" signal, so it must be
the code for *any* behavioral regression or below-threshold result. Everything else
(config, infra, safety) uses a distinct non-1 code so a real gate failure is never
confused with a broken pipeline.
"""

from __future__ import annotations

OK: int = 0
"""Gate passed (or a non-gate command succeeded)."""

GATE_FAILED: int = 1
"""Completion regressed vs. baseline, or fell below the threshold. The CI signal."""

CONFIG_ERROR: int = 2
"""Bad/missing sim.yml, unknown flow, or invalid arguments."""

RUN_ERROR: int = 3
"""The swarm itself crashed (browser/Holo/infra) — no verdict was produced."""

UNSAFE_URL: int = 4
"""Target URL rejected by the SSRF guard (see cli/safety.py)."""

__all__ = ["OK", "GATE_FAILED", "CONFIG_ERROR", "RUN_ERROR", "UNSAFE_URL"]
