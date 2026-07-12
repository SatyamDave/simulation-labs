"""CLI: ``python -m ghostpanel.benchmarks [--live] [--cases ...] [--personas ...]``.

Prints a scoreboard and writes the full JSON report under
``artifacts/benchmarks/bench-<epoch>.json`` (or ``--json PATH``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from .harness import BUILTIN_CASES, format_scoreboard, run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ghostpanel.benchmarks")
    parser.add_argument("--live", action="store_true",
                        help="use the real Holo API (needs HAI_API_KEY); default is offline")
    parser.add_argument("--cases", default=None,
                        help=f"comma-separated case ids ({', '.join(c.id for c in BUILTIN_CASES)}); default all")
    parser.add_argument("--personas", default=None,
                        help="comma-separated persona ids; default the full roster")
    parser.add_argument("--json", default=None, metavar="PATH",
                        help="where to write the JSON report")
    args = parser.parse_args()

    case_ids = args.cases.split(",") if args.cases else None
    persona_ids = args.personas.split(",") if args.personas else None

    report = asyncio.run(run_benchmark(case_ids=case_ids, persona_ids=persona_ids,
                                       live=args.live))

    out = Path(args.json) if args.json else (
        Path("artifacts/benchmarks") / f"bench-{int(time.time())}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    print(format_scoreboard(report))
    print(f"\nJSON report: {out}")


if __name__ == "__main__":
    main()
