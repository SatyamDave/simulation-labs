"""build_heatmap: abandonments in -> weighted HeatPoints within viewport
bounds; success and infra-error personas contribute nothing."""

from ghostpanel_contracts import PersonaConfig, PersonaOutcome, PersonaResult
from ghostpanel_contracts.contracts import Viewport

from ghostpanel.report.heatmap import build_heatmap


def _result(persona_id, outcome, coords=None):
    return PersonaResult(persona_id=persona_id, outcome=outcome, failure_coords=coords)


def test_failures_become_points_success_and_error_do_not(fixture_results):
    # fixture: grandma-72 stuck at (300, 145); power-user success
    points = build_heatmap(fixture_results)
    assert [(p.x, p.y, p.persona_id) for p in points] == [(300, 145, "grandma-72")]
    assert all(p.weight == 1.0 for p in points)


def test_error_and_missing_coords_are_skipped():
    results = [
        _result("crash-dummy", PersonaOutcome.ERROR, coords=(10, 10)),
        _result("no-coords", PersonaOutcome.STUCK, coords=None),
    ]
    assert build_heatmap(results) == []


def test_points_clamped_to_persona_viewport():
    persona = PersonaConfig(
        id="impatient-mobile", name="Priya", viewport=Viewport(width=390, height=844)
    )
    results = [_result("impatient-mobile", PersonaOutcome.TIME_BUDGET, coords=(500, 900))]
    (point,) = build_heatmap(results, personas=[persona])
    assert (point.x, point.y) == (389, 843)


def test_unknown_persona_clamps_to_default_viewport():
    results = [_result("mystery", PersonaOutcome.STUCK, coords=(2000, -5))]
    (point,) = build_heatmap(results)
    assert (point.x, point.y) == (1279, 0)  # contract default 1280x800


def test_clustering_sums_weights():
    results = [
        _result("grandma-72", PersonaOutcome.STUCK, coords=(300, 145)),
        _result("low-vision", PersonaOutcome.STUCK, coords=(292, 150)),
        _result("tremor", PersonaOutcome.STEP_BUDGET, coords=(170, 372)),
    ]
    points = build_heatmap(results, cluster_radius=24)
    assert len(points) == 2
    merged = next(p for p in points if p.weight == 2.0)
    assert 292 <= merged.x <= 300 and 145 <= merged.y <= 150
    lone = next(p for p in points if p.weight == 1.0)
    assert (lone.x, lone.y) == (170, 372)


def test_no_clustering_by_default():
    results = [
        _result("grandma-72", PersonaOutcome.STUCK, coords=(300, 145)),
        _result("low-vision", PersonaOutcome.STUCK, coords=(292, 150)),
    ]
    assert len(build_heatmap(results)) == 2
