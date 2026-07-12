"""NemoClaw-mirror policy tests: RequestPolicy semantics + real enforcement.

Unit tests exercise the OpenShell-preset semantics (method allow-list, host
globs, ``/**`` path globs, monitor vs enforce, deny-by-default). The
integration test drives a real headless Chromium at a localhost http.server
page whose form POSTs, with the SHIPPED ``policies/ghostpanel-browse-only.yaml``
preset installed — and proves the POST is aborted before it reaches the server
while navigation GETs flow normally.
"""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from ghostpanel.runner.policy import RequestPolicy
from ghostpanel.runner.session import PlaywrightSessionRunner
from ghostpanel.runner.testing import CollectingEventSink, StubPersonaAgent
from ghostpanel_contracts import (
    Action,
    ActionType,
    PersonaConfig,
    PersonaOutcome,
    StepEvent,
    Viewport,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PRESET_PATH = REPO_ROOT / "policies" / "ghostpanel-browse-only.yaml"
VIEWPORT = {"width": 1280, "height": 900}

_FORM_HTML = """<!doctype html>
<html><head><title>Checkout</title></head>
<body>
  <h1>Checkout</h1>
  <form method="POST" action="/submit">
    <input type="text" name="card" value="4111-1111-1111-1111">
    <button id="pay" type="submit" style="width:220px;height:64px;font-size:20px">
      Pay now
    </button>
  </form>
</body></html>
"""


# ---------------------------------------------------------------------------
# RequestPolicy semantics (no browser)
# ---------------------------------------------------------------------------
def test_shipped_preset_allows_get_denies_every_write_verb():
    policy = RequestPolicy.from_file(PRESET_PATH)
    assert policy.preset_name == "ghostpanel-browse-only"

    assert policy.allows("GET", "https://example.com/pricing") is True
    assert policy.allows("get", "http://any.host.test/deep/path?x=1") is True
    # The mirror matches host+method+path; ports are the gateway's job.
    assert policy.allows("GET", "http://127.0.0.1:54321/fixtures/page.html") is True

    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert policy.allows(verb, "https://example.com/checkout") is False, verb
    assert policy.allows("POST", "http://127.0.0.1:54321/submit") is False


def test_host_wildcard_matching_and_deny_for_unlisted_hosts():
    policy = RequestPolicy(
        {
            "preset": {"name": "subdomains-only"},
            "network_policies": {
                "p": {
                    "endpoints": [
                        {
                            "host": "*.trusted.test",
                            "port": 443,
                            "protocol": "rest",
                            "enforcement": "enforce",
                            "rules": [{"allow": {"method": "GET", "path": "/**"}}],
                        }
                    ]
                }
            },
        }
    )
    assert policy.allows("GET", "https://api.trusted.test/v1/things") is True
    assert policy.allows("GET", "https://API.Trusted.TEST/v1") is True  # case-insensitive
    # Apex doesn't match the subdomain glob; unlisted hosts are denied outright
    # (the client-side mirror has no operator to escalate to).
    assert policy.allows("GET", "https://trusted.test/") is False
    assert policy.allows("GET", "https://evil.test/") is False
    assert policy.allows("POST", "https://api.trusted.test/v1/things") is False


def test_path_glob_semantics():
    policy = RequestPolicy(
        {
            "preset": {"name": "paths"},
            "network_policies": {
                "p": {
                    "endpoints": [
                        {
                            "host": "*",
                            "port": 443,
                            "enforcement": "enforce",
                            "rules": [
                                {"allow": {"method": "GET", "path": "/public/**"}},
                                {"allow": {"method": "GET", "path": "/api/*/status"}},
                            ],
                        }
                    ]
                }
            },
        }
    )
    # ** crosses segments…
    assert policy.allows("GET", "https://h.test/public/a/b/c.html") is True
    assert policy.allows("GET", "https://h.test/private/a") is False
    # …a single * stays within one segment.
    assert policy.allows("GET", "https://h.test/api/v1/status") is True
    assert policy.allows("GET", "https://h.test/api/v1/extra/status") is False
    # Method still gates even on an allowed path.
    assert policy.allows("POST", "https://h.test/public/a") is False


def test_monitor_endpoints_never_block():
    policy = RequestPolicy(
        {
            "preset": {"name": "monitored"},
            "network_policies": {
                "p": {
                    "endpoints": [
                        {
                            "host": "*",
                            "port": 443,
                            "enforcement": "monitor",
                            "rules": [{"allow": {"method": "GET", "path": "/**"}}],
                        }
                    ]
                }
            },
        }
    )
    assert policy.allows("POST", "https://h.test/anything") is True


def test_summary_shape_matches_get_policy_contract():
    policy = RequestPolicy.from_file(PRESET_PATH)
    assert policy.summary() == {
        "preset": "ghostpanel-browse-only",
        "allowed_methods": ["GET"],
        "denied_by_default": True,
        "hosts": ["*"],
    }


# ---------------------------------------------------------------------------
# Real enforcement: PlaywrightSessionRunner aborts a form POST
# ---------------------------------------------------------------------------
@pytest.fixture
async def browser():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        yield b
        await b.close()


@pytest.fixture
def form_site(tmp_path):
    """Serve a POSTing checkout form; yield (base_url, request_log)."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "form.html").write_text(_FORM_HTML, encoding="utf-8")
    log: list[tuple[str, str]] = []

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            log.append(("GET", self.path))
            super().do_GET()

        def do_POST(self):
            log.append(("POST", self.path))
            body = b"charged!"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(site))
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", log
    server.shutdown()
    server.server_close()


async def test_runner_blocks_form_post_with_browse_only_preset(
    browser, tmp_path, form_site
):
    base_url, log = form_site
    target_url = f"{base_url}/form.html"

    # Measure the true center of the Pay button (no click here — just geometry).
    ctx = await browser.new_context(viewport=VIEWPORT)
    p = await ctx.new_page()
    await p.goto(target_url)
    box = await p.locator("#pay").bounding_box()
    pay = (int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2))
    await ctx.close()

    persona = PersonaConfig(
        id="payer",
        name="Payer",
        viewport=Viewport(width=VIEWPORT["width"], height=VIEWPORT["height"]),
        max_steps=6,
        deadline_s=60.0,
    )
    script = [
        Action(type=ActionType.CLICK, x=pay[0], y=pay[1], caption="click Pay now"),
        Action(type=ActionType.WAIT, seconds=0.5, caption="waiting"),
    ]
    sink = CollectingEventSink()
    runner = PlaywrightSessionRunner(
        browser,
        tmp_path / "artifacts",
        policy=RequestPolicy.from_file(PRESET_PATH),
    )
    result = await runner.run(
        persona, StubPersonaAgent(persona, script), target_url, "buy", sink, "run-policy"
    )

    # Blocking never crashed the session: script exhaustion -> ANSWER -> success.
    assert result.outcome == PersonaOutcome.SUCCESS

    # The navigation GET flowed; the POST was aborted BEFORE reaching the server.
    assert ("GET", "/form.html") in log
    assert not any(method == "POST" for method, _ in log)

    # (a) The step got EXACTLY "policy_blocked" as its note — the report module
    # counts blocked actions with strict equality on that string.
    noted = [s for s in result.steps if s.note == "policy_blocked"]
    assert noted, f"no policy_blocked note in {[s.note for s in result.steps]}"

    # (b) A shield StepEvent was emitted for the blocked request.
    shields = [
        e
        for e in sink.events
        if isinstance(e, StepEvent) and e.caption.startswith("🛡 Policy blocked")
    ]
    assert shields, "no 🛡 StepEvent emitted"
    assert shields[0].caption == "🛡 Policy blocked POST 127.0.0.1"
    # Exactly one shield per step — the handler must not spam the grid.
    assert len({e.step for e in shields}) == len(shields)
