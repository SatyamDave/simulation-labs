"""Soft, optional Sentry wiring for the Ghostpanel orchestrator.

Sentry is a **soft dependency**: it is intentionally NOT in ``pyproject.toml``.
This module never hard-imports ``sentry_sdk`` at module load — the import is
guarded inside :func:`init_sentry` so the app runs identically whether or not
the package is installed. When the DSN is empty *or* ``sentry_sdk`` is missing,
initialization is a no-op that returns ``False``; the caller (``app.py``) treats
that as "error reporting disabled" and carries on.

Public surface the composition root uses:

  * :func:`init_sentry(dsn)` -> ``bool`` — attempt init, report whether it took.
  * :func:`configure(app, settings)` -> ``bool`` — read the DSN + tuning from the
    environment (never mutating ``Settings``) and call :func:`init_sentry`.

The small helpers (:func:`env_dsn`, :func:`resolve_traces_sample_rate`,
:func:`environment_name`) are pure and unit-testable in isolation.
"""

from __future__ import annotations

import logging
import os
from typing import Any

_LOG = logging.getLogger("ghostpanel.observability")

# Environment variable names (read directly from os.environ; we do NOT touch the
# frozen Settings dataclass).
ENV_SENTRY_DSN = "SENTRY_DSN"
ENV_TRACES_SAMPLE_RATE = "SENTRY_TRACES_SAMPLE_RATE"
ENV_RELEASE = "SENTRY_RELEASE"
# Reuse the app's deployment-env name if present, falling back to a generic one.
ENV_ENVIRONMENT = "GHOSTPANEL_ENV"

# Conservative default: sample 10% of traces so a production DSN doesn't cost a
# fortune or add latency. Overridable via SENTRY_TRACES_SAMPLE_RATE.
DEFAULT_TRACES_SAMPLE_RATE = 0.1


def resolve_traces_sample_rate(
    raw: str | None, *, default: float = DEFAULT_TRACES_SAMPLE_RATE
) -> float:
    """Parse a traces-sample-rate string into a float clamped to ``[0.0, 1.0]``.

    Pure/unit-testable. ``None``/blank/garbage all fall back to ``default``;
    out-of-range values are clamped rather than rejected.
    """
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return default
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def env_dsn(environ: dict[str, str] | None = None) -> str:
    """Return the (stripped) Sentry DSN from the environment, or ``""``.

    Pure: pass ``environ`` for tests, defaults to ``os.environ``.
    """
    source = os.environ if environ is None else environ
    return (source.get(ENV_SENTRY_DSN) or "").strip()


def environment_name(
    settings: Any = None, environ: dict[str, str] | None = None
) -> str:
    """Best-effort deployment-environment tag for Sentry events.

    Prefers ``settings.env`` when a Settings-like object is supplied, else the
    ``GHOSTPANEL_ENV`` env var, else ``"dev"``. Never raises.
    """
    source = os.environ if environ is None else environ
    env = getattr(settings, "env", None)
    if isinstance(env, str) and env.strip():
        return env.strip()
    return (source.get(ENV_ENVIRONMENT) or "dev").strip() or "dev"


def init_sentry(
    dsn: str,
    *,
    traces_sample_rate: float = DEFAULT_TRACES_SAMPLE_RATE,
    environment: str | None = None,
    release: str | None = None,
) -> bool:
    """Initialize Sentry if possible; return whether it actually initialized.

    Contract:
      * empty/blank ``dsn`` -> return ``False`` (reporting disabled, no import);
      * ``sentry_sdk`` not installed -> log a one-line note, return ``False``
        (soft dependency: never a hard failure);
      * otherwise call ``sentry_sdk.init(...)`` and return ``True``. Any error
        from ``init`` is swallowed (logged) and reported as ``False`` so a
        misconfigured DSN can never take the process down.
    """
    if not dsn or not str(dsn).strip():
        return False

    try:
        import sentry_sdk  # soft/optional dep — guarded on purpose
    except ImportError:
        _LOG.info(
            "sentry_sdk not installed; error reporting disabled "
            "(install 'sentry-sdk' to enable). DSN was provided."
        )
        return False

    try:
        sentry_sdk.init(
            dsn=str(dsn).strip(),
            traces_sample_rate=float(traces_sample_rate),
            environment=environment,
            release=release,
        )
    except Exception:  # noqa: BLE001 - a bad DSN must never crash startup
        _LOG.exception("sentry_sdk.init failed; continuing without Sentry")
        return False

    _LOG.info("Sentry initialized (environment=%s)", environment)
    return True


def configure(app: Any = None, settings: Any = None) -> bool:
    """Convenience helper the app can call once at startup.

    Reads ``SENTRY_DSN`` (and optional ``SENTRY_TRACES_SAMPLE_RATE`` /
    ``SENTRY_RELEASE``) from the environment — it does NOT read or mutate the
    frozen ``Settings`` object except to borrow ``settings.env`` as the Sentry
    environment tag. Returns whether Sentry was initialized.

    ``app`` is accepted for API symmetry / future middleware wiring; Sentry's
    ASGI integration hooks itself in globally on ``init``, so nothing needs to
    be attached to ``app`` today.
    """
    dsn = env_dsn()
    rate = resolve_traces_sample_rate(os.environ.get(ENV_TRACES_SAMPLE_RATE))
    release = (os.environ.get(ENV_RELEASE) or "").strip() or None
    environment = environment_name(settings)
    return init_sentry(
        dsn,
        traces_sample_rate=rate,
        environment=environment,
        release=release,
    )


__all__ = [
    "ENV_SENTRY_DSN",
    "ENV_TRACES_SAMPLE_RATE",
    "ENV_RELEASE",
    "ENV_ENVIRONMENT",
    "DEFAULT_TRACES_SAMPLE_RATE",
    "resolve_traces_sample_rate",
    "env_dsn",
    "environment_name",
    "init_sentry",
    "configure",
]
