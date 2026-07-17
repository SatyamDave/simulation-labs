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
        persona_ids=["fluent"],
        artifact_dir=tmp_path,
        browser=browser,
    )
    assert report["mode"] == "offline"
    assert report["personas"] == ["fluent"]
    (case,) = report["cases"]
    assert case["case"] == "easy"
    (row,) = case["personas"]
    # FakeHoloClient center-clicks forever -> the stuck detector ends the session.
    assert row["outcome"] == "stuck"
    assert row["steps"] >= 3
    assert row["wall_s"] > 0
    assert row["overhead_ms_per_step"] > 0


async def test_scripted_success_counts_as_completion(browser, tmp_path):
    from ghostpanel.benchmarks.harness import _REPO_ROOT

    # A genuine completion of easy_form: fill both fields (each WRITE presses
    # Enter; the second submits once both are non-empty) so #ok becomes visible.
    # A bare ANSWER would (correctly) be rejected as unverified — the runner
    # requires the success predicate to confirm a claimed completion.
    url = f"file://{_REPO_ROOT / 'benchmarks' / 'pages' / 'easy_form.html'}"
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await ctx.new_page()
    await page.goto(url)

    def _center(box):
        return (int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2))

    email = _center(await page.locator("#email").bounding_box())
    pw = _center(await page.locator("#pw").bounding_box())
    await ctx.close()

    script = [
        Action(type=ActionType.WRITE, x=email[0], y=email[1], text="me@work.com", caption="type email"),
        Action(type=ActionType.WRITE, x=pw[0], y=pw[1], text="hunter2pass", caption="type password"),
    ]

    def factory(persona, holo, task):
        return StubPersonaAgent(persona, list(script))

    report = await run_benchmark(
        case_ids=["easy"],
        persona_ids=["fluent"],
        artifact_dir=tmp_path,
        agent_factory=factory,
        browser=browser,
    )
    (case,) = report["cases"]
    assert case["completion_rate"] == 1.0
    assert case["mean_steps_to_success"] == 2.0


async def test_scoreboard_renders(browser, tmp_path):
    report = await run_benchmark(
        case_ids=["easy"],
        persona_ids=["fluent"],
        artifact_dir=tmp_path,
        browser=browser,
    )
    board = format_scoreboard(report)
    assert "[easy]" in board
    assert "fluent" in board


def test_unknown_case_raises():
    with pytest.raises(ValueError):
        import asyncio

        asyncio.run(run_benchmark(case_ids=["nope"]))
