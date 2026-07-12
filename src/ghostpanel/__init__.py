"""Ghostpanel — behavioral synthetic users powered by H Company Holo.

Package layout (one owner per subpackage — see CLAUDE.md file-ownership map):
    engine/  — Agent 1: Holo client, persona agent, perturbations, persona configs
    runner/  — Agent 2: Playwright session runner
    server/  — Agent 3: FastAPI orchestrator, swarm manager, composition root
    voice/   — Agent 5: Gradium voice engine
    report/  — Agent 5: survival/heatmap report builder
"""

__version__ = "0.1.0"
