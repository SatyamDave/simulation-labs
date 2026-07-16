"""SRE metrics tests — the hand-rolled Prometheus ``/metrics`` endpoint.

Covers: ``/metrics`` returns 200 text with HELP/TYPE lines; hitting a route
increments ``http_requests_total`` for it; ``inc_run``/``inc_job`` surface in the
exposition; the latency histogram emits ``_bucket``/``_sum``/``_count`` with a
``+Inf`` bucket; and path normalization collapses id segments to ``:id``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ghostpanel.server.metrics import (
    CONTENT_TYPE,
    HTTP_REQUESTS,
    add_metrics,
    inc_job,
    inc_run,
    normalize_path,
    render_prometheus,
)


@pytest.fixture()
def client():
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    add_metrics(app)

    with TestClient(app) as c:
        yield c


def test_metrics_endpoint_returns_text(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "version=0.0.4" in resp.headers["content-type"]
    body = resp.text
    # Every metric declares HELP + TYPE lines.
    assert "# HELP http_requests_total" in body
    assert "# TYPE http_requests_total counter" in body
    assert "# HELP http_request_duration_seconds" in body
    assert "# TYPE http_request_duration_seconds histogram" in body
    assert "# TYPE runs_total counter" in body
    assert "# TYPE jobs_total counter" in body


def test_content_type_constant():
    assert CONTENT_TYPE.startswith("text/plain")
    assert "0.0.4" in CONTENT_TYPE


def test_http_requests_increments_after_a_request(client):
    before = _sample_value(
        HTTP_REQUESTS.collect(), 'http_requests_total{path="/ping",method="GET",status="200"}'
    )

    resp = client.get("/ping")
    assert resp.status_code == 200

    body = client.get("/metrics").text
    line = _find_line(
        body, 'http_requests_total{path="/ping",method="GET",status="200"}'
    )
    assert line is not None, body
    after = float(line.rsplit(" ", 1)[1])
    assert after == before + 1


def test_latency_histogram_shape(client):
    client.get("/ping")
    body = client.get("/metrics").text
    assert 'http_request_duration_seconds_bucket{path="/ping",le="0.005"}' in body
    assert 'http_request_duration_seconds_bucket{path="/ping",le="+Inf"}' in body
    assert 'http_request_duration_seconds_sum{path="/ping"}' in body
    count_line = _find_line(
        body, 'http_request_duration_seconds_count{path="/ping"}'
    )
    assert count_line is not None
    assert float(count_line.rsplit(" ", 1)[1]) >= 1


def test_histogram_buckets_are_cumulative_and_le_inf_equals_count(client):
    for _ in range(3):
        client.get("/ping")
    body = client.get("/metrics").text
    inf = _sample_value(
        body.splitlines(),
        'http_request_duration_seconds_bucket{path="/ping",le="+Inf"}',
    )
    count = _sample_value(
        body.splitlines(), 'http_request_duration_seconds_count{path="/ping"}'
    )
    assert inf == count >= 3


def test_inc_run_and_inc_job_surface_in_exposition():
    inc_run("success")
    inc_run("stuck")
    inc_job("running")
    text = render_prometheus()
    assert 'runs_total{outcome="success"}' in text
    assert 'runs_total{outcome="stuck"}' in text
    assert 'jobs_total{state="running"}' in text


def test_inc_run_accepts_enum_like():
    class _Outcome:
        value = "time_budget"

    inc_run(_Outcome())
    assert 'runs_total{outcome="time_budget"}' in render_prometheus()


def test_render_ends_with_newline():
    assert render_prometheus().endswith("\n")


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "/v2/runs/3f2504e0-4f89-41d3-9a0c-0305e82c3301",
            "/v2/runs/:id",
        ),
        ("/v2/runs/12345", "/v2/runs/:id"),
        ("/v2/runs/12345/artifacts/report.html", "/v2/runs/:id/artifacts/report.html"),
        ("/v2/runs/deadbeefdeadbeef99", "/v2/runs/:id"),  # long hex
        ("/v2/runs", "/v2/runs"),  # unchanged
        ("/metrics", "/metrics"),
    ],
)
def test_path_normalization(raw, expected):
    assert normalize_path(raw) == expected


def test_middleware_uses_route_template_for_matched_route():
    """A matched route with a path param records the template, not a raw id."""
    app = FastAPI()

    @app.get("/v2/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, str]:
        return {"run_id": run_id}

    add_metrics(app)
    with TestClient(app) as c:
        c.get("/v2/runs/abc-123")
        body = c.get("/metrics").text
    # Template form (low cardinality) is used when routing resolved one.
    assert 'path="/v2/runs/{run_id}"' in body


def test_label_value_escaping():
    from ghostpanel.server.metrics import Counter

    c = Counter("weird_total", "help", ("k",))
    c.inc(k='a"b\\c')
    body = "\n".join(c.collect())
    assert 'weird_total{k="a\\"b\\\\c"} 1' in body


# --- helpers ---------------------------------------------------------------
def _find_line(text_or_lines, series: str) -> str | None:
    lines = text_or_lines.splitlines() if isinstance(text_or_lines, str) else text_or_lines
    for line in lines:
        if line.startswith(series + " "):
            return line
    return None


def _sample_value(lines, exact_series: str) -> float:
    for line in lines:
        if line.startswith(exact_series + " "):
            return float(line.rsplit(" ", 1)[1])
    return 0.0
