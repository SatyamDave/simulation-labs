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

# --- Preflight codes (added for the founder-run manual-audit path) -----------
# These extend, and never reassign, the frozen 0..4 above: CI still keys on
# GATE_FAILED (1), and every below distinguishes a *specific* pre-run failure so
# the founder (and any wrapping script) can tell "bad config" from "no key" from
# "typo'd persona" from "site down" at a glance, without reading the message.

MISSING_KEY: int = 5
"""A live model backend was selected but its API key is absent (use --fixture)."""

UNKNOWN_PERSONA: int = 6
"""One or more requested persona ids are not in the bundled roster (likely typo)."""

UNREACHABLE_URL: int = 7
"""The target host does not resolve / cannot be reached (typo or site is down)."""

OUTPUT_ERROR: int = 8
"""The output directory could not be created or is not writable."""

NO_RESULTS: int = 9
"""The swarm ran but produced zero usable results (every persona hit an infra error)."""

INTERRUPTED: int = 130
"""The run was interrupted with Ctrl-C (SIGINT); standard 128+SIGINT convention."""

__all__ = [
    "OK", "GATE_FAILED", "CONFIG_ERROR", "RUN_ERROR", "UNSAFE_URL",
    "MISSING_KEY", "UNKNOWN_PERSONA", "UNREACHABLE_URL", "OUTPUT_ERROR",
    "NO_RESULTS", "INTERRUPTED",
]
