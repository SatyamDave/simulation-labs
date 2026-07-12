"""Benchmark-harness tests — hermetic (FakeHoloClient / stub agents, local HTTP)."""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from ghostpanel.benchmarks import BUILTIN_CASES, format_scoreboard, run_benchmark
from ghostpanel.runner.testing import StubPersonaAgent
from ghostpanel_contracts import Action, ActionType


@pytest.fixture
async def browser():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        yield b
        await b.close()


def test_builtin_case_pages_exist():
    from ghostpanel.benchmarks.harness import _REPO_ROOT

    for case in BUILTIN_CASES:
        assert (_REPO_ROOT / case.page).is_file(), case.page


async def test_offline_benchmark_produces_metrics(browser, tmp_path):
    report = await run_benchmark(
        case_ids=["easy"],
        persona_ids=["power-user"],
        artifact_dir=tmp_path,
        browser=browser,
    )
    assert report["mode"] == "offline"
    assert report["personas"] == ["power-user"]
    (case,) = report["cases"]
    assert case["case"] == "easy"
    (row,) = case["personas"]
    # FakeHoloClient center-clicks forever -> the stuck detector ends the session.
    assert row["outcome"] == "stuck"
    assert row["steps"] >= 3
    assert row["wall_s"] > 0
    assert row["overhead_ms_per_step"] > 0


async def test_scripted_success_counts_as_completion(browser, tmp_path):
    def factory(persona, holo, task):
        return StubPersonaAgent(
            persona, [Action(type=ActionType.ANSWER, text="done", caption="done")]
        )

    report = await run_benchmark(
        case_ids=["easy"],
        persona_ids=["power-user", "tremor"],
        artifact_dir=tmp_path,
        agent_factory=factory,
        browser=browser,
    )
    (case,) = report["cases"]
    assert case["completion_rate"] == 1.0
    assert case["mean_steps_to_success"] == 1.0


async def test_scoreboard_renders(browser, tmp_path):
    report = await run_benchmark(
        case_ids=["easy"],
        persona_ids=["power-user"],
        artifact_dir=tmp_path,
        browser=browser,
    )
    board = format_scoreboard(report)
    assert "[easy]" in board
    assert "power-user" in board


def test_unknown_case_raises():
    with pytest.raises(ValueError):
        import asyncio

        asyncio.run(run_benchmark(case_ids=["nope"]))
