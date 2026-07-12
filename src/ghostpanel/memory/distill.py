"""Pure, deterministic distillation of a finished run into memory records.

No LLM, no I/O, no ``supermemory`` import — everything here is offline-testable.
``SupermemoryStore.remember_run`` calls :func:`distill_run` to turn a
:class:`RunReport` (plus the personas that produced it) into a flat list of
``(content, container_tags, metadata)`` records ready for ``documents.add``.

Three kinds of record are emitted (see ``store.py`` for the tag scheme):

  * ``site_playbook`` — one per non-error persona, keyed to ``site_tag(url)``.
  * ``insight``       — one per NON-success, non-error persona, keyed to
                        ``INSIGHTS_TAG`` (powers GET /insights).
  * ``persona_visit`` — one per non-error persona, keyed to
                        ``persona_site_tag(id, url)`` (returning-user memory).

Metadata is ALWAYS flat: values are ``str | int | float | bool | list[str]``.
``None`` values are dropped so a metadata dict never carries a null.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ghostpanel_contracts import PersonaConfig, PersonaOutcome, RunReport

from .store import (
    INSIGHTS_TAG,
    domain_slug,
    impairment_key,
    persona_site_tag,
    site_tag,
)

# Record kinds (also written into metadata["kind"] for later filtering).
KIND_SITE_PLAYBOOK = "site_playbook"
KIND_INSIGHT = "insight"
KIND_PERSONA_VISIT = "persona_visit"

_MetaValue = object  # str | int | float | bool | list[str] after _flat drops None


@dataclass(frozen=True)
class DistilledRecord:
    """One memory ready to write: natural-language ``content`` + its container
    tags + FLAT metadata (no nested dicts, no ``None`` values)."""

    content: str
    container_tags: list[str]
    metadata: dict = field(default_factory=dict)
    custom_id_kind: str = ""  # e.g. "site_playbook" — combined with run_id+persona upstream


def _flat(**kwargs: _MetaValue) -> dict:
    """Build a metadata dict, dropping keys whose value is ``None`` so the result
    only ever holds ``str | int | float | bool | list[str]``."""
    return {k: v for k, v in kwargs.items() if v is not None}


def _snippet(text: str, limit: int = 200) -> str:
    """Trim an exit-interview transcript to a short, single-line signal."""
    if not text:
        return ""
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def distill_run(
    *,
    target_url: str,
    task: str,
    report: RunReport,
    personas: list[PersonaConfig],
    run_id: str = "",
) -> list[DistilledRecord]:
    """Join ``report.results`` + ``report.survival`` to each ``PersonaConfig``
    (by id) and produce the memory records for a finished run."""
    personas_by_id = {p.id: p for p in personas}
    survival_by_id = {s.persona_id: s for s in report.survival}
    domain = domain_slug(target_url)
    site = site_tag(target_url)

    records: list[DistilledRecord] = []

    for result in report.results:
        pid = result.persona_id
        outcome = result.outcome
        # Infra failures pollute every knowledge base — never remember them.
        if outcome == PersonaOutcome.ERROR:
            continue

        persona = personas_by_id.get(pid)
        surv = survival_by_id.get(pid)
        name = (persona.name if persona else "") or (surv.persona_name if surv else "") or pid
        impairment = impairment_key(persona) if persona else "unknown"
        steps_survived = (
            surv.steps_survived if surv is not None else len(result.steps)
        )
        outcome_str = outcome.value
        is_success = outcome == PersonaOutcome.SUCCESS

        coords = result.failure_coords
        fx = int(coords[0]) if coords else None
        fy = int(coords[1]) if coords else None
        fstep = result.failure_step
        reason = result.failure_reason or ""
        transcript = _snippet(result.transcript)

        base_meta = _flat(
            kind=None,  # set per-record below
            site=domain,
            persona_id=pid,
            persona_name=name,
            impairment=impairment,
            outcome=outcome_str,
            steps_survived=steps_survived,
            failure_x=fx,
            failure_y=fy,
            failure_step=fstep,
            run_id=run_id or None,
        )

        # --- content strings (shared by site playbook + returning-user memory) ---
        if is_success:
            headline = f"Completed '{task}' on {domain} in {steps_survived} steps."
        else:
            where = f" near ({fx},{fy})" if fx is not None else ""
            at = f" at step {fstep}" if fstep is not None else ""
            detail = f": {reason}" if reason else "."
            headline = (
                f"A {impairment} user ({name}) abandoned '{task}' on "
                f"{domain}{at}{where}{detail}"
            )
        if transcript:
            headline = f"{headline} Exit interview: “{transcript}”"

        # 1) SITE PLAYBOOK — every non-error persona contributes.
        records.append(
            DistilledRecord(
                content=headline,
                container_tags=[site],
                metadata={**base_meta, "kind": KIND_SITE_PLAYBOOK},
                custom_id_kind=KIND_SITE_PLAYBOOK,
            )
        )

        # 2) INSIGHT — only real abandonments (non-success, non-error).
        if not is_success:
            records.append(
                DistilledRecord(
                    content=headline,
                    container_tags=[INSIGHTS_TAG],
                    metadata={**base_meta, "kind": KIND_INSIGHT},
                    custom_id_kind=KIND_INSIGHT,
                )
            )

        # 3) RETURNING-USER memory — the persona's own recollection of this visit.
        if persona is not None:
            if is_success:
                visit = (
                    f"On a prior visit to {domain} you completed '{task}' "
                    f"in {steps_survived} steps."
                )
            else:
                where = f" near ({fx},{fy})" if fx is not None else ""
                at = f" at step {fstep}" if fstep is not None else ""
                detail = f": {reason}" if reason else "."
                visit = (
                    f"On a prior visit to {domain} you tried to '{task}' but "
                    f"gave up{at}{where}{detail}"
                )
            records.append(
                DistilledRecord(
                    content=visit,
                    container_tags=[persona_site_tag(persona.id, target_url)],
                    metadata={**base_meta, "kind": KIND_PERSONA_VISIT},
                    custom_id_kind=KIND_PERSONA_VISIT,
                )
            )

    return records
