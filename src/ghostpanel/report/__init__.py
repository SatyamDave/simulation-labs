"""Report — Agent 5. Survival curves, abandonment heatmap, RunReport + HTML artifact.

Two HTML renderers live here:
  * ``html_report`` — the internal/technical leave-behind (score, stats, WCAG
    evidence). Used by the server today.
  * ``deliverable`` — the polished, findings-first, CRO-framed client report that
    is hand-delivered as a single self-contained ``report.html``.
    ``write_deliverable_report`` is a drop-in for ``write_html_report``.
"""

from .builder import SurvivalReportBuilder
from .deliverable import render_deliverable, write_deliverable_report
from .html_report import render_html, write_html_report
from .insights import build_insights

__all__ = [
    "SurvivalReportBuilder",
    "build_insights",
    "render_html",
    "write_html_report",
    "render_deliverable",
    "write_deliverable_report",
]
