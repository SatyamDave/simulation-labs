"""Abandonment heatmap — aggregate failure coordinates into weighted HeatPoints.

Every persona that *abandoned* (non-success, non-error) died at a specific pixel
(`PersonaResult.failure_coords`). This module turns those pixels into
`HeatPoint`s the frontend renders as blobs. ERROR outcomes are excluded: an
infra crash is not a human giving up, so it must not paint the page.
"""

from __future__ import annotations

import math
from typing import Optional

from ghostpanel_contracts import HeatPoint, PersonaConfig, PersonaOutcome, PersonaResult
from ghostpanel_contracts.contracts import Viewport

_DEFAULT_VIEWPORT = Viewport()  # 1280 x 800 contract default


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def build_heatmap(
    results: list[PersonaResult],
    personas: Optional[list[PersonaConfig]] = None,
    cluster_radius: float = 0.0,
) -> list[HeatPoint]:
    """Turn abandonment coordinates into weighted HeatPoints.

    Args:
        results: one PersonaResult per persona in the run.
        personas: used to clamp each point to its persona's viewport bounds;
            personas not found fall back to the contract-default 1280x800.
        cluster_radius: if > 0, greedily merge points within this pixel radius,
            summing their weights (centroid is weight-averaged). 0 disables
            clustering (one point per abandonment, like fixtures/run.json).

    Returns:
        HeatPoints for every non-success, non-error result that recorded
        failure_coords. Success and error personas contribute nothing.
    """
    viewport_by_id: dict[str, Viewport] = {p.id: p.viewport for p in (personas or [])}

    points: list[HeatPoint] = []
    for result in results:
        if result.outcome in (PersonaOutcome.SUCCESS, PersonaOutcome.ERROR):
            continue
        if result.failure_coords is None:
            continue
        x, y = result.failure_coords
        vp = viewport_by_id.get(result.persona_id, _DEFAULT_VIEWPORT)
        points.append(
            HeatPoint(
                x=_clamp(x, 0, vp.width - 1),
                y=_clamp(y, 0, vp.height - 1),
                weight=1.0,
                persona_id=result.persona_id,
            )
        )

    if cluster_radius > 0:
        points = _cluster(points, cluster_radius)
    return points


def _cluster(points: list[HeatPoint], radius: float) -> list[HeatPoint]:
    """Greedy single-pass clustering: fold each point into the first existing
    cluster within `radius`, summing weights and weight-averaging the centroid.
    The cluster keeps the persona_id of its first contributor."""
    clusters: list[HeatPoint] = []
    for pt in points:
        merged = False
        for i, c in enumerate(clusters):
            if math.dist((pt.x, pt.y), (c.x, c.y)) <= radius:
                total = c.weight + pt.weight
                clusters[i] = HeatPoint(
                    x=round((c.x * c.weight + pt.x * pt.weight) / total),
                    y=round((c.y * c.weight + pt.y * pt.weight) / total),
                    weight=total,
                    persona_id=c.persona_id,
                )
                merged = True
                break
        if not merged:
            clusters.append(pt.model_copy())
    return clusters
