"""Persona loader tests.

The PUBLIC roster is the four behavioral segments + the Fluent baseline. The
accessibility personas (low-vision, colorblind, ...) are retired to
personas/_advanced/ (not loaded by load_personas) but their mechanical
capabilities remain in the engine and the PersonaConfig contract.
"""

from __future__ import annotations

from pathlib import Path

from ghostpanel.engine.personas import load_personas
from ghostpanel_contracts import CVDType, PersonaConfig

PUBLIC_IDS = {"fluent", "rushed", "misclick-prone", "first-timer", "mobile-thumb"}


def test_load_all_personas():
    personas = load_personas()
    assert len(personas) >= 5
    assert all(isinstance(p, PersonaConfig) for p in personas)


def test_persona_ids_unique():
    personas = load_personas()
    ids = [p.id for p in personas]
    assert len(ids) == len(set(ids))


def test_public_roster_is_behavioral_segments():
    ids = {p.id for p in load_personas()}
    assert PUBLIC_IDS <= ids


def test_accessibility_personas_retired_from_public_roster():
    ids = {p.id for p in load_personas()}
    for retired in {"low-vision", "colorblind", "grandma-72"}:
        assert retired not in ids


def test_filter_by_ids_preserves_order():
    want = ["misclick-prone", "fluent", "first-timer"]
    personas = load_personas(want)
    assert [p.id for p in personas] == want


def test_filter_unknown_id_skipped():
    personas = load_personas(["fluent", "does-not-exist"])
    assert [p.id for p in personas] == ["fluent"]


def test_misclick_persona_has_tremor():
    (m,) = load_personas(["misclick-prone"])
    assert m.tremor_sigma_px > 0


def test_cvd_capability_retained_in_contract():
    # The colorblind persona is retired from the public roster, but the CVD
    # perturbation capability must remain in the engine/contract for later use.
    cfg = PersonaConfig(id="_cvd", name="CVD", cvd_type=CVDType.DEUTAN, cvd_severity=0.9)
    assert cfg.cvd_type is CVDType.DEUTAN and cfg.cvd_severity > 0


def test_retired_personas_still_valid_on_disk():
    # _advanced/*.json are not in the public roster but must remain valid configs
    # (reversible retirement — we may promote them back later).
    adv = Path(__file__).resolve().parents[2] / "personas" / "_advanced"
    files = list(adv.glob("*.json"))
    assert files, "expected retired personas under personas/_advanced/"
    for f in files:
        PersonaConfig.model_validate_json(f.read_text(encoding="utf-8"))
