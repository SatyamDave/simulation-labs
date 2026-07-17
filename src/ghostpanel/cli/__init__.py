"""Simulation Labs CLI (`sim`) — the CI-first behavioral-test wrapper around the
Ghostpanel engine.

No server required: `driver.run_flow` wires the existing engine/runner/report
modules directly and drives a headless swarm to a `RunReport`. The CLI turns that
report into a pass/fail gate (`regression.compare`) and CI-native output
(`ci_output`). See `PHASE1_SPEC.md` at the repo root for module ownership and the
frozen interfaces every submodule implements.
"""

from .exit_codes import (
    CONFIG_ERROR,
    GATE_FAILED,
    INTERRUPTED,
    MISSING_KEY,
    NO_RESULTS,
    OK,
    OUTPUT_ERROR,
    RUN_ERROR,
    UNKNOWN_PERSONA,
    UNREACHABLE_URL,
    UNSAFE_URL,
)

__all__ = [
    "OK", "GATE_FAILED", "CONFIG_ERROR", "RUN_ERROR", "UNSAFE_URL",
    "MISSING_KEY", "UNKNOWN_PERSONA", "UNREACHABLE_URL", "OUTPUT_ERROR",
    "NO_RESULTS", "INTERRUPTED",
]
