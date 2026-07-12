"""Tests for build_heatmap: failure coords -> clamped HeatPoints; success -> none."""

from __future__ import annotations

from ghostpanel_contracts import HeatPoint, PersonaOutcome, PersonaResult

from ghostpanel.report.heatmap import DEFAULT_VIEWPORT, build_heatmap


def test_only_non_success_with_coords_contribute():
    results = [
        PersonaResult(
            persona_id="grandma-72",
            outcome=PersonaOutcome.STUCK,
            failure_coords=(300, 145),
        ),
        PersonaResult(
            persona_id="power-user",
            outcome=PersonaOutcome.SUCCESS,
            failure_coords=None,
        ),
        # non-success but no recorded coords -> contributes nothing
        PersonaResult(
            persona_id="no-coords",
            outcome=PersonaOutcome.STUCK,
            failure_coords=None,
        ),
    ]
    points = build_heatmap(results)
    assert len(points) == 1
    assert isinstance(points[0], HeatPoint)
    assert points[0].persona_id == "grandma-72"
    assert (points[0].x, points[0].y) == (300, 145)
    assert points[0].weight == 1.0


def test_success_persona_even_with_coords_contributes_nothing():
    # defensive: a SUCCESS outcome never abandons, even if coords leaked in
    results = [
        PersonaResult(
            persona_id="winner",
            outcome=PersonaOutcome.SUCCESS,
            failure_coords=(10, 10),
        )
    ]
    assert build_heatmap(results) == []


def test_coords_are_clamped_to_viewport():
    width, height = DEFAULT_VIEWPORT
    results = [
        PersonaResult(
            persona_id="out-high",
            outcome=PersonaOutcome.STUCK,
            failure_coords=(99999, 88888),
        ),
        PersonaResult(
            persona_id="out-low",
            outcome=PersonaOutcome.STUCK,
            failure_coords=(-40, -5),
        ),
    ]
    points = build_heatmap(results)
    for p in points:
        assert 0 <= p.x <= width - 1
        assert 0 <= p.y <= height - 1
    by_id = {p.persona_id: p for p in points}
    assert (by_id["out-high"].x, by_id["out-high"].y) == (width - 1, height - 1)
    assert (by_id["out-low"].x, by_id["out-low"].y) == (0, 0)
