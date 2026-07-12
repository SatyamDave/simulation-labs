"""Aggregate persona abandonment coordinates into weighted heatmap points.

The frontend renders the blobs; we just supply weighted `HeatPoint`s. Only
non-success personas that actually died at a recorded pixel contribute a point.
"""

from __future__ import annotations

from ghostpanel_contracts import HeatPoint, PersonaOutcome, PersonaResult

# Default viewport used to clamp stray coordinates. Personas may run in smaller
# viewports, but their failure coords are always in true viewport pixels; we
# clamp to a sane maximum so a bad coordinate can never blow up the render.
DEFAULT_VIEWPORT = (1280, 800)


def build_heatmap(
    results: list[PersonaResult],
    viewport: tuple[int, int] = DEFAULT_VIEWPORT,
) -> list[HeatPoint]:
    """Turn each non-success `failure_coords` into a clamped `HeatPoint`.

    Success personas contribute nothing (they did not abandon). Coordinates are
    clamped into ``[0, width-1] x [0, height-1]`` so an out-of-bounds pixel can
    never escape the viewport.
    """
    width, height = viewport
    max_x = max(width - 1, 0)
    max_y = max(height - 1, 0)

    points: list[HeatPoint] = []
    for result in results:
        if result.outcome == PersonaOutcome.SUCCESS:
            continue
        if result.failure_coords is None:
            continue
        raw_x, raw_y = result.failure_coords
        x = min(max(int(raw_x), 0), max_x)
        y = min(max(int(raw_y), 0), max_y)
        points.append(
            HeatPoint(x=x, y=y, weight=1.0, persona_id=result.persona_id)
        )
    return points
