"""Tests for the pure distillation layer (no network, no SDK)."""

from __future__ import annotations

from ghostpanel.memory.distill import (
    KIND_INSIGHT,
    KIND_PERSONA_VISIT,
    KIND_SITE_PLAYBOOK,
    distill_run,
)
from ghostpanel.memory.store import INSIGHTS_TAG, persona_site_tag, site_tag

_FLAT_TYPES = (str, int, float, bool)


def _assert_flat(meta: dict) -> None:
    """Every metadata value must be str|int|float|bool|list[str] and never None."""
    for k, v in meta.items():
        assert v is not None, f"metadata[{k!r}] is None"
        if isinstance(v, list):
            assert all(isinstance(x, str) for x in v), f"metadata[{k!r}] not list[str]"
        else:
            assert isinstance(v, _FLAT_TYPES), f"metadata[{k!r}] is {type(v)}"


def test_error_persona_excluded_everywhere(report, personas):
    recs = distill_run(
        target_url=report.target_url, task=report.task, report=report,
        personas=personas, run_id=report.run_id,
    )
    assert all(r.metadata.get("persona_id") != "crashed-bot" for r in recs)


def test_all_metadata_flat(report, personas):
    recs = distill_run(
        target_url=report.target_url, task=report.task, report=report,
        personas=personas, run_id=report.run_id,
    )
    assert recs
    for r in recs:
        _assert_flat(r.metadata)
        assert r.metadata["kind"] in {
            KIND_SITE_PLAYBOOK, KIND_INSIGHT, KIND_PERSONA_VISIT
        }


def test_record_counts_and_tags(report, personas):
    recs = distill_run(
        target_url=report.target_url, task=report.task, report=report,
        personas=personas, run_id=report.run_id,
    )
    site = site_tag(report.target_url)

    playbooks = [r for r in recs if r.custom_id_kind == KIND_SITE_PLAYBOOK]
    insights = [r for r in recs if r.custom_id_kind == KIND_INSIGHT]
    visits = [r for r in recs if r.custom_id_kind == KIND_PERSONA_VISIT]

    # 3 non-error personas → 3 playbooks + 3 persona visits; 2 abandonments → 2 insights.
    assert len(playbooks) == 3
    assert len(visits) == 3
    assert len(insights) == 2

    assert all(r.container_tags == [site] for r in playbooks)
    assert all(r.container_tags == [INSIGHTS_TAG] for r in insights)
    # insights are only abandonments — never the success.
    assert {r.metadata["persona_id"] for r in insights} == {"grandma-70", "impatient-mobile"}


def test_persona_visit_tag_is_scoped(report, personas):
    recs = distill_run(
        target_url=report.target_url, task=report.task, report=report,
        personas=personas, run_id=report.run_id,
    )
    grandma = next(
        r for r in recs
        if r.custom_id_kind == KIND_PERSONA_VISIT and r.metadata["persona_id"] == "grandma-70"
    )
    assert grandma.container_tags == [persona_site_tag("grandma-70", report.target_url)]


def test_success_content(report, personas):
    recs = distill_run(
        target_url=report.target_url, task=report.task, report=report,
        personas=personas, run_id=report.run_id,
    )
    playbook = next(
        r for r in recs
        if r.custom_id_kind == KIND_SITE_PLAYBOOK and r.metadata["persona_id"] == "power-user"
    )
    assert "Completed" in playbook.content
    assert "12 steps" in playbook.content
    assert playbook.metadata["outcome"] == "success"


def test_abandon_content_mentions_impairment_and_failure(report, personas):
    recs = distill_run(
        target_url=report.target_url, task=report.task, report=report,
        personas=personas, run_id=report.run_id,
    )
    insight = next(
        r for r in recs
        if r.custom_id_kind == KIND_INSIGHT and r.metadata["persona_id"] == "grandma-70"
    )
    # impairment key is derived from perturbations (blur+tremor, sorted).
    assert insight.metadata["impairment"] == "blur+tremor"
    assert "blur+tremor" in insight.content
    assert "Margaret" in insight.content
    assert "step 7" in insight.content
    assert "(412,388)" in insight.content
    assert "couldn't find the submit button" in insight.content
    # transcript snippet folded in.
    assert "Exit interview" in insight.content
    assert insight.metadata["failure_x"] == 412
    assert insight.metadata["failure_y"] == 388
    assert insight.metadata["failure_step"] == 7
    assert insight.metadata["steps_survived"] == 7
    assert insight.metadata["run_id"] == "run-abc"


def test_abandon_without_coords_has_no_failure_xy(report, personas):
    recs = distill_run(
        target_url=report.target_url, task=report.task, report=report,
        personas=personas, run_id=report.run_id,
    )
    insight = next(
        r for r in recs
        if r.custom_id_kind == KIND_INSIGHT and r.metadata["persona_id"] == "impatient-mobile"
    )
    assert "failure_x" not in insight.metadata
    assert "failure_y" not in insight.metadata
    assert insight.metadata["failure_step"] == 3


def test_run_id_optional_omitted_when_blank(report, personas):
    recs = distill_run(
        target_url=report.target_url, task=report.task, report=report,
        personas=personas,  # no run_id
    )
    assert all("run_id" not in r.metadata for r in recs)
