"""Persona loader tests."""

from __future__ import annotations

import pytest

from ghostpanel.engine.personas import load_personas
from ghostpanel_contracts import PersonaConfig


def test_load_all_personas():
    personas = load_personas()
    assert len(personas) >= 6
    assert all(isinstance(p, PersonaConfig) for p in personas)


def test_persona_ids_unique():
    personas = load_personas()
    ids = [p.id for p in personas]
    assert len(ids) == len(set(ids))


def test_expected_ids_present():
    ids = {p.id for p in load_personas()}
    for expected in {"grandma-72", "low-vision", "colorblind", "tremor", "power-user"}:
        assert expected in ids


def test_filter_by_ids_preserves_order():
    want = ["tremor", "power-user", "colorblind"]
    personas = load_personas(want)
    assert [p.id for p in personas] == want


def test_filter_unknown_id_skipped():
    personas = load_personas(["power-user", "does-not-exist"])
    assert [p.id for p in personas] == ["power-user"]


def test_colorblind_has_cvd():
    (cb,) = load_personas(["colorblind"])
    assert cb.cvd_type is not None and cb.cvd_severity > 0


def test_tremor_persona_has_tremor():
    (t,) = load_personas(["tremor"])
    assert t.tremor_sigma_px > 0
