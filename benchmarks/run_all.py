"""Run the Ghostpanel benchmark suite and build the aggregate HTML report.

Usage:
    python -m benchmarks.run_all              # offline + analytic only (no API)
    python -m benchmarks.run_all --live       # also run A1 + B (spends Holo budget)
    python -m benchmarks.run_all --report     # just rebuild report.html from results/

Offline benchmarks are deterministic (seeded); live ones respect HAI_RPM.
"""

from __future__ import annotations

import sys

from benchmarks import common as c

OFFLINE = [
    "benchmarks.b_a2_tremor_wcag",
    "benchmarks.b_a3_invariants",
    "benchmarks.b_c2_throughput",
    "benchmarks.b_c3_overhead",
    "benchmarks.b_d1_classifiers",
]
LIVE = [
    "benchmarks.b_a1_localization",
    "benchmarks.b_b_survival",
]


def _run_module(modname: str) -> None:
    import runpy

    print(f"\n===== {modname} =====")
    runpy.run_module(modname, run_name="__main__")


def main(argv: list[str]) -> None:
    c.load_env()
    if "--report" not in argv:
        for m in OFFLINE:
            _run_module(m)
        if "--live" in argv:
            for m in LIVE:
                _run_module(m)

    path = c.build_report()
    print(f"\nReport written: {path}")
    print(f"Results: {len(c.load_results())} benchmarks in {c.RESULTS_DIR}")


if __name__ == "__main__":
    main(sys.argv[1:])
