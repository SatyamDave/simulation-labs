"""Tests for the grounding eval gate (tests/engine/grounding_eval.py).

The offline tests use ``FakeHoloClient`` so they run in CI with no network — they
prove the harness's plumbing (image sizing, distance math, scoring, reporting) is
correct. The live test runs the real gate only when inference credentials are
configured, and skips gracefully otherwise.
"""

from __future__ import annotations

import os

import pytest

from ghostpanel.engine.holo_client import FakeHoloClient
from ghostpanel.engine.selfhost_client import (
    DEFAULT_SELFHOST_BASE_URL,
    SelfHostedHoloClient,
)
from ghostpanel_contracts import HoloClient

from .grounding_eval import (
    EvalReport,
    GroundingCase,
    default_cases,
    make_button_case,
    run_grounding_eval,
)


class _SeqLocalizeClient:
    """A minimal HoloClient that returns queued coords, one per localize call.

    ``FakeHoloClient.localize`` only ever peeks the head of its script (it never
    advances), so it can't emulate a per-case-perfect model across a multi-case
    suite. This tiny sequential client does, and still satisfies the
    ``@runtime_checkable`` HoloClient Protocol.
    """

    def __init__(self, coords: list[tuple[int, int]]) -> None:
        self._coords = list(coords)
        self._i = 0

    async def localize(self, image_png: bytes, instruction: str) -> tuple[int, int]:
        c = self._coords[self._i]
        self._i += 1
        return c

    async def navigate(self, image_png: bytes, task: str, history: list[str]):
        from ghostpanel_contracts import Action, ActionType

        x, y = self._coords[min(self._i, len(self._coords) - 1)]
        return Action(type=ActionType.CLICK, x=x, y=y, caption="seq")


# ---------------------------------------------------------------------------
# Self-hosted client contract checks
# ---------------------------------------------------------------------------
def test_selfhost_client_satisfies_holoclient_protocol():
    client = SelfHostedHoloClient()
    assert isinstance(client, HoloClient)


def test_selfhost_client_defaults_to_local_endpoint():
    client = SelfHostedHoloClient()
    assert client.base_url == DEFAULT_SELFHOST_BASE_URL
    assert client.model == "Hcompany/Holo-3.1-35B-A3B"
    # No vendor cap: the limiter refills fast enough to never block a swarm.
    assert client.rpm >= 1000


def test_selfhost_registered_in_model_registry():
    from ghostpanel.engine.models import available

    assert "selfhost" in available()


# ---------------------------------------------------------------------------
# Deterministic case construction
# ---------------------------------------------------------------------------
def test_button_case_is_deterministic():
    a = make_button_case("x", "click it", button_xywh=(100, 100, 80, 40))
    b = make_button_case("x", "click it", button_xywh=(100, 100, 80, 40))
    assert a.image_png == b.image_png  # byte-for-byte reproducible
    assert a.expected == (140, 120)  # centre of the drawn rectangle


def test_default_cases_include_fixture():
    names = {c.name for c in default_cases()}
    assert "synthetic_center_button" in names
    assert "fixture_sample_screenshot" in names


# ---------------------------------------------------------------------------
# Offline smoke test: a perfect client scores 100%
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_eval_scores_perfect_client_100pct():
    cases = [
        make_button_case("c1", "click it", button_xywh=(220, 200, 200, 60)),
        make_button_case("c2", "click it", size=(800, 600), button_xywh=(600, 40, 150, 50)),
    ]
    # A perfect model that returns each case's exact target pixel, in order.
    perfect = _SeqLocalizeClient([c.expected for c in cases])
    assert isinstance(perfect, HoloClient)
    report = await run_grounding_eval(perfect, cases)
    assert isinstance(report, EvalReport)
    assert report.total == 2
    assert report.passed == 2
    assert report.accuracy == 1.0
    assert report.mean_distance == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_eval_scores_off_target_client_as_fail():
    # A far-off target with a tight tolerance must score as a miss.
    case = GroundingCase(
        name="miss",
        image_png=make_button_case("_", "_").image_png,
        instruction="click it",
        expected=(600, 400),
        tolerance_px=10.0,
    )
    fake = FakeHoloClient(scripted_actions=[(10, 10)])
    report = await run_grounding_eval(fake, [case])
    assert report.accuracy == 0.0
    assert report.results[0].passed is False
    assert report.results[0].distance > 10.0


@pytest.mark.asyncio
async def test_eval_runs_default_suite_without_error():
    # Empty fake -> center clicks. This is the CI smoke test: the gate RUNS end
    # to end on every case (incl. the real fixture) without raising.
    fake = FakeHoloClient()
    report = await run_grounding_eval(fake, default_cases())
    assert report.total == len(default_cases())
    assert all(r.error == "" for r in report.results)  # no case crashed
    # A center-clicking fake trivially passes the lenient fixture case.
    assert report.accuracy > 0.0


@pytest.mark.asyncio
async def test_report_format_is_human_readable():
    fake = FakeHoloClient()
    report = await run_grounding_eval(fake, default_cases()[:1])
    text = report.format()
    assert "accuracy" in text
    assert "%" in text


# ---------------------------------------------------------------------------
# Live gate: only runs when credentials are configured.
# ---------------------------------------------------------------------------
_LIVE = os.getenv("HAI_API_KEY") or os.getenv("GROUNDING_EVAL_BACKEND") == "selfhost"


@pytest.mark.skipif(
    not _LIVE,
    reason="no inference endpoint configured; set HAI_API_KEY (hosted) or "
    "GROUNDING_EVAL_BACKEND=selfhost + HAI_BASE_URL to run the live gate",
)
@pytest.mark.asyncio
async def test_live_grounding_gate_meets_threshold():
    from .grounding_eval import _build_live_client

    client = _build_live_client()
    if client is None:
        pytest.skip("no usable inference credentials")
    report = await run_grounding_eval(client, default_cases())
    print("\n" + report.format())
    # Gate threshold for a shippable backend. Loosen/tighten as the suite grows.
    assert report.accuracy >= 0.5, report.format()
