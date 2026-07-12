"""Persona catalogue tests: personas/*.json load and validate."""

import pytest

from ghostpanel.engine.personas import load_personas
from ghostpanel_contracts import CVDType, PersonaConfig

EXPECTED_IDS = {
    "grandma-72", "low-vision", "colorblind", "tremor",
    "impatient-mobile", "non-native", "power-user", "ai-agent",
}


def test_load_all_personas():
    personas = load_personas()
    assert len(personas) >= 6
    assert all(isinstance(p, PersonaConfig) for p in personas)
    ids = [p.id for p in personas]
    assert len(ids) == len(set(ids)), "persona ids must be unique"
    assert EXPECTED_IDS <= set(ids)


def test_filter_by_ids_preserves_requested_order():
    personas = load_personas(ids=["tremor", "grandma-72"])
    assert [p.id for p in personas] == ["tremor", "grandma-72"]


def test_unknown_id_raises():
    with pytest.raises(KeyError):
        load_personas(ids=["does-not-exist"])


def test_key_perturbations_wired():
    by_id = {p.id: p for p in load_personas()}

    assert by_id["grandma-72"].blur_sigma > 0
    assert by_id["grandma-72"].literacy_note
    assert by_id["grandma-72"].max_steps <= 15

    assert by_id["low-vision"].blur_sigma > 0
    assert 0 < by_id["low-vision"].downscale_factor < 1

    assert by_id["colorblind"].cvd_type is CVDType.DEUTAN
    assert by_id["colorblind"].cvd_severity >= 0.8

    assert by_id["tremor"].tremor_sigma_px >= 10

    assert (by_id["impatient-mobile"].viewport.width,
            by_id["impatient-mobile"].viewport.height) == (390, 844)
    assert by_id["impatient-mobile"].deadline_s <= 60

    assert by_id["non-native"].language != "en"
    assert by_id["non-native"].literacy_note

    # controls: no degradation at all
    for control in ("power-user", "ai-agent"):
        p = by_id[control]
        assert p.blur_sigma == 0 and p.downscale_factor == 1.0
        assert p.cvd_type is None and p.tremor_sigma_px == 0
        assert p.active_perturbations == []
