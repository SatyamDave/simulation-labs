"""Bundled demo flow for ``sim try`` — a self-contained proof that the gate works.

Ships the signup page inline (no package-data needed), serves it on a loopback
port, and hands back the URL. The page has a deliberately small 24px consent
checkbox: a steady hand completes it, an imprecise/tremor segment fumbles it and
abandons — the whole point of the gate, visible in one command.
"""

from __future__ import annotations

import functools
import http.server
import socket
import threading
from pathlib import Path

DEMO_SIGNUP_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Create your account | Nimbus</title>
<style>
  *{ box-sizing:border-box; }
  body{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
    color:#0f1222; background:#f6f8fc; -webkit-font-smoothing:antialiased; }
  .wrap{ min-height:100vh; display:flex; align-items:center; justify-content:center; padding:40px 16px; }
  .card{ width:100%; max-width:400px; background:#fff; border:1px solid #e5e7eb; border-radius:14px;
    box-shadow:0 8px 30px rgba(16,24,40,.06); padding:32px 30px 28px; }
  .brand{ display:flex; align-items:center; gap:9px; margin-bottom:22px; }
  .brand .dot{ width:22px; height:22px; border-radius:6px; background:linear-gradient(135deg,#5C98FF,#2E68D8); }
  .brand b{ font-size:1.05rem; letter-spacing:-.01em; }
  h1{ font-size:1.4rem; letter-spacing:-.02em; margin:0 0 4px; }
  .sub{ color:#6b7280; font-size:.92rem; margin:0 0 22px; }
  label{ display:block; font-size:.82rem; font-weight:600; color:#374151; margin:0 0 6px; }
  .field{ margin-bottom:16px; }
  input[type=email],input[type=password],input[type=text]{ width:100%; height:52px; padding:0 13px;
    border:1px solid #d5dae2; border-radius:9px; font-size:.95rem; outline:none; }
  input:focus{ border-color:#4C8DFF; box-shadow:0 0 0 3px rgba(76,141,255,.15); }
  .consent{ display:flex; align-items:center; gap:11px; margin:8px 0 20px; }
  .consent input{ width:24px; height:24px; margin:0; flex:0 0 auto; accent-color:#4C8DFF; cursor:pointer; }
  .consent .consent-text{ font-weight:400; font-size:.86rem; color:#374151; line-height:1.35; }
  .consent .consent-text a{ color:#2E68D8; }
  .cta{ width:100%; height:46px; border:0; border-radius:9px; font-size:.98rem; font-weight:600;
    color:#fff; background:#4C8DFF; cursor:pointer; }
  .err{ color:#c02636; font-size:.82rem; margin:-8px 0 14px; min-height:1em; }
  .foot{ text-align:center; font-size:.85rem; color:#6b7280; margin-top:18px; }
  .foot a{ color:#2E68D8; }
  .done{ text-align:center; padding:18px 6px; }
  .done .check{ width:56px; height:56px; border-radius:50%; background:#e7f6ec; color:#1a9c4b;
    display:flex; align-items:center; justify-content:center; font-size:1.9rem; margin:0 auto 16px; }
  .done h2{ margin:0 0 6px; font-size:1.35rem; }
  .done p{ color:#6b7280; margin:0; }
  [hidden]{ display:none !important; }
</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="brand"><span class="dot"></span><b>Nimbus</b></div>
      <form id="form">
        <h1>Create your account</h1>
        <p class="sub">Start your 14-day free trial. No card required.</p>
        <div class="field">
          <label for="email">Work email</label>
          <input id="email" type="email" autocomplete="email" placeholder="you@company.com" />
        </div>
        <div class="field">
          <label for="password">Password</label>
          <input id="password" type="password" autocomplete="new-password" placeholder="At least 8 characters" />
        </div>
        <div class="consent">
          <input id="agree" type="checkbox" aria-label="I agree to the Terms of Service and Privacy Policy" />
          <span class="consent-text">I agree to the <a href="#" onclick="return false">Terms of Service</a> and <a href="#" onclick="return false">Privacy Policy</a>.</span>
        </div>
        <p class="err" id="err"></p>
        <button class="cta" type="submit">Create account</button>
        <p class="foot">Already have an account? <a href="#" onclick="return false">Sign in</a></p>
      </form>
      <div class="done" id="done" hidden>
        <div class="check">&#10003;</div>
        <h2>You're in!</h2>
        <p>Your Nimbus account is ready. Redirecting to your dashboard&hellip;</p>
      </div>
    </div>
  </div>
  <script>
    var form = document.getElementById('form');
    var done = document.getElementById('done');
    var err  = document.getElementById('err');
    var BROKEN = /(?:^|[?&])broken=1(?:&|$)/.test(location.search);
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var email = document.getElementById('email').value.trim();
      var pw    = document.getElementById('password').value.trim();
      var agree = document.getElementById('agree').checked;
      if (!email || email.indexOf('@') === -1) { err.textContent = 'Enter a valid email address.'; return; }
      if (pw.length < 8) { err.textContent = 'Password must be at least 8 characters.'; return; }
      if (!agree) { err.textContent = 'Please agree to the Terms of Service to continue.'; return; }
      err.textContent = '';
      if (BROKEN) { return; }
      form.setAttribute('hidden', '');
      done.removeAttribute('hidden');
    });
  </script>
</body>
</html>
"""

DEMO_TASK = (
    "Sign up: enter a work email and a password (8+ chars), tick the small "
    "'I agree to the Terms' checkbox until it is checked, then click Create "
    "account. You are done only when you see 'You're in!'."
)
# The behavioral segments the demo sends (undegraded controls + degraded users).
DEMO_PERSONAS = ["fluent", "ai-agent", "rushed", "mobile-thumb", "misclick-prone"]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Serves DEMO_SIGNUP_HTML for any path; silent (no request logging)."""

    def log_message(self, *args) -> None:  # noqa: D401, ANN002
        pass

    def do_GET(self) -> None:  # noqa: N802
        body = DEMO_SIGNUP_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class DemoServer:
    """Context manager that serves the demo flow on a loopback port."""

    def __init__(self) -> None:
        self.port = _free_port()
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), _QuietHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/signup"

    def __enter__(self) -> "DemoServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
