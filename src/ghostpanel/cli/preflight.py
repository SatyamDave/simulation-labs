"""Preflight validation for the founder-run manual-audit path — Agent A owns this.

Before a `sim run` (or `gate`/`baseline`) burns wall-clock, quota, and a client's
patience against a live production site, we check the cheap, offline things first
and the network things last, and turn every failure into a **one-line human
message + a distinct exit code** — never a traceback.

Order matters (cheapest / most-local first so we fail fast and never contact a
target we're about to refuse anyway):

    1. requested persona ids exist        -> UNKNOWN_PERSONA
    2. output directory is writable        -> OUTPUT_ERROR
    3. target URL is well-formed           -> CONFIG_ERROR
    4. target host resolves (reachable)    -> UNREACHABLE_URL
    5. SSRF guard (safety.assert_url_allowed) -> UnsafeURLError (=> UNSAFE_URL)
    6. model API key present for live run  -> MISSING_KEY

`--fixture` runs skip 3-6 entirely (offline file:// + FakeHoloClient), but still
validate personas and the output dir. The SSRF check is delegated to `safety`
unchanged — we never weaken it, we just run it in sequence so its refusal keeps
its own distinct exit code.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlsplit

from . import exit_codes, safety

if TYPE_CHECKING:  # avoid an import cycle at runtime (main imports preflight)
    from .main import _RunParams


class PreflightError(Exception):
    """A preflight check failed. Carries the human message + the CLI exit code."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ---------------------------------------------------------------------------
# Individual checks (each raises PreflightError with a distinct code)
# ---------------------------------------------------------------------------
def check_personas(persona_ids: Optional[list[str]]) -> None:
    """Fail (listing the valid ids) if any requested persona id is unknown.

    ``persona_ids is None`` means "the full roster" — always valid. This guards
    the swarm's silent fallback: ``load_personas`` drops unknown ids and, when
    that empties the list, ``SwarmManager.start_run`` quietly runs the whole
    roster instead — so a typo'd ``--personas grandma`` would run the wrong swarm
    with no warning. We catch it here."""
    if not persona_ids:
        return
    # Late import so `--fixture`/offline tests don't pull the engine unless needed.
    from ghostpanel.engine.personas import load_personas

    valid = {p.id for p in load_personas(None)}
    unknown = [pid for pid in persona_ids if pid not in valid]
    if unknown:
        known = ", ".join(sorted(valid)) or "(none found)"
        raise PreflightError(
            f"unknown persona id(s): {', '.join(unknown)}. "
            f"Valid ids: {known}.",
            exit_codes.UNKNOWN_PERSONA,
        )


def check_output_dir(out_dir: Path) -> None:
    """Fail if the output directory can't be created or written to."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / ".sim_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise PreflightError(
            f"output dir {out_dir} is not writable: {exc.strerror or exc}. "
            f"Pass --out PATH to a directory you can write to.",
            exit_codes.OUTPUT_ERROR,
        ) from exc


def check_url_wellformed(url: str) -> None:
    """Fail if `url` isn't a syntactically valid http(s) target with a host."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if not scheme:
        raise PreflightError(
            f"target {url!r} is not a URL: it has no scheme. "
            f"Did you mean https://{url}?",
            exit_codes.CONFIG_ERROR,
        )
    if scheme not in ("http", "https"):
        # `file://` never reaches here (fixtures skip URL checks); anything else
        # (ftp, javascript, data, …) is a config mistake, not an SSRF attempt.
        raise PreflightError(
            f"unsupported URL scheme {scheme!r} in {url!r}: point --url at an "
            f"http(s) page, e.g. https://your-app.example.com/signup.",
            exit_codes.CONFIG_ERROR,
        )
    if not parts.hostname:
        raise PreflightError(
            f"target {url!r} has no host. Give a full URL like "
            f"https://your-app.example.com/signup.",
            exit_codes.CONFIG_ERROR,
        )


def check_reachable(url: str) -> None:
    """Fail if the target host does not resolve in DNS.

    DNS resolution (a query to the *resolver*, not the target) is a cheap, safe
    reachability probe — we do NOT open a TCP connection here, which would be an
    SSRF vector; the SSRF guard runs next and inspects the resolved addresses.
    Resolution failing is the common "typo'd domain / site is gone" signal, and
    getting its own exit code keeps it distinct from a genuine SSRF refusal."""
    host = urlsplit(url).hostname
    if not host:  # already reported by check_url_wellformed; defensive.
        return
    try:
        socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise PreflightError(
            f"cannot reach {host!r}: DNS lookup failed ({exc.strerror or exc}). "
            f"Check the URL is spelled correctly and the site is up. "
            f"For a local/staging target, set safety.allow_private: true in "
            f"sim.yml (or use --fixture for an offline HTML file).",
            exit_codes.UNREACHABLE_URL,
        ) from exc


def check_local_server_up(url: str, allow_private: bool) -> None:
    """For an explicitly opted-in LOOPBACK target, fail fast if nothing is
    listening on its port.

    DNS always resolves localhost/127.0.0.1, so `check_reachable` can't catch a
    forgotten ``python -m http.server`` — every persona would then ERROR on
    page.goto mid-run. A TCP connect is normally an SSRF vector, but here it is
    safe: it only runs when the operator set ``allow_private: true`` AND the host
    is loopback (the demo case), never against arbitrary/remote targets."""
    if not allow_private:
        return
    parts = urlsplit(url)
    host = parts.hostname
    if host not in ("localhost", "127.0.0.1", "::1"):
        return
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return
    except OSError as exc:
        raise PreflightError(
            f"demo server not reachable on {host}:{port} — is it running? "
            f"Start it with `python -m http.server {port}` from the repo root, "
            f"then re-run.",
            exit_codes.UNREACHABLE_URL,
        ) from exc


def check_model_key() -> None:
    """Fail if a live model backend is selected but its API key is missing.

    Only the ``holo`` backend needs ``HAI_API_KEY``; ``selfhost``/``echo`` don't.
    Fixture runs never call this (they use the offline FakeHoloClient)."""
    from ghostpanel.engine.models.registry import default_backend
    from ghostpanel.server.config import get_settings

    backend = (default_backend() or "").strip().lower()
    if backend != "holo":
        return  # selfhost / echo need no vendor key
    if not get_settings().hai_api_key.strip():
        raise PreflightError(
            "no model API key: set HAI_API_KEY in .env for a live run "
            "(or use --fixture for offline testing, or MODEL_BACKEND=selfhost/echo).",
            exit_codes.MISSING_KEY,
        )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_preflight(params: "_RunParams") -> None:
    """Run every preflight check in order. Raises PreflightError on the first
    failure, or safety.UnsafeURLError from the SSRF guard. Returns None if all
    checks pass (the run is safe to start)."""
    check_personas(params.persona_ids)
    check_output_dir(params.out_dir)

    if params.fixture:
        return  # offline file:// + FakeHoloClient: no URL/key checks apply.

    check_url_wellformed(params.url)
    check_reachable(params.url)
    # SSRF guard — unchanged; raises safety.UnsafeURLError (=> UNSAFE_URL).
    safety.assert_url_allowed(
        params.url, allow_private=params.allow_private, allowlist=params.allowlist
    )
    # Only after the SSRF guard has OK'd an explicitly-allowed loopback target do
    # we probe that the demo server is actually up (safe: opted-in loopback only).
    check_local_server_up(params.url, params.allow_private)
    check_model_key()


# ---------------------------------------------------------------------------
# In-run resilience helpers (advisory text, not validation)
# ---------------------------------------------------------------------------
def rate_limit_notice(params: "_RunParams") -> Optional[str]:
    """A one-line heads-up when a live run will be throttled by the shared RPM cap.

    The free Holo tier is ~5 rpm and the whole swarm shares it, so N personas
    running against a real site take a while. Warn up front so the founder isn't
    surprised mid-demo. Returns None for fixture runs or an uncapped backend."""
    if params.fixture:
        return None
    try:
        from ghostpanel.engine.models.registry import default_backend
        from ghostpanel.server.config import get_settings

        backend = (default_backend() or "").strip().lower()
        if backend != "holo":
            return None  # selfhost/echo aren't vendor-rate-limited
        settings = get_settings()
        rpm = float(params.rpm) if params.rpm is not None else float(settings.hai_rpm)
    except Exception:  # noqa: BLE001 - advisory only; never block a run
        return None
    if rpm <= 0:
        return None
    n = len(params.persona_ids) if params.persona_ids else None
    who = f"{n} personas" if n else "the full roster"
    return (
        f"note: live Holo runs are rate-limited (~{rpm:.0f} requests/min, shared "
        f"across the swarm) — {who} will be slow; leave it running."
    )


def classify_run_error(error: Optional[str]) -> Optional[str]:
    """Turn a raw swarm error string into an actionable one-liner, when we
    recognise it (rate-limit, network drop). Returns None when we don't."""
    if not error:
        return None
    low = error.lower()
    if "429" in low or "rate limit" in low or "rate-limit" in low or "too many requests" in low:
        return (
            "hint: the model API rate-limited the swarm (429). Lower --rpm, send "
            "fewer --personas, or upgrade the Holo plan, then re-run."
        )
    if any(
        s in low
        for s in ("connection", "timed out", "timeout", "getaddrinfo",
                  "network", "econnreset", "name resolution", "unreachable")
    ):
        return (
            "hint: this looks like a network problem reaching the target or the "
            "model API. Check your connection and that the site is up, then re-run."
        )
    return None


def usable_results(report) -> int:
    """Count results that carry real behavioral signal (not an infra ERROR).

    Zero means the report is not worth showing a client — every persona crashed
    before it could act. Prefer the per-persona ``results`` (the real builder
    always fills these); fall back to the ``survival`` summary when ``results``
    is empty so a report that only carries a survival curve still counts."""
    from ghostpanel_contracts import PersonaOutcome

    if report.results:
        return sum(1 for r in report.results if r.outcome != PersonaOutcome.ERROR)
    return len(report.survival)


__all__ = [
    "PreflightError",
    "run_preflight",
    "check_personas",
    "check_output_dir",
    "check_url_wellformed",
    "check_reachable",
    "check_model_key",
    "rate_limit_notice",
    "classify_run_error",
    "usable_results",
]
