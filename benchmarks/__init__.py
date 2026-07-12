"""Ghostpanel benchmark suite.

Each module benchmarks/b_*.py measures one thing and writes a JSON result to
benchmarks/results/<id>.json via common.write_result(). run_all.py runs them all
and common.build_report() renders results/report.html.

Offline benchmarks are deterministic (seeded numpy, no network). Live benchmarks
call the real Holo API through the engine's LiveHoloClient and respect HAI_RPM.
"""
