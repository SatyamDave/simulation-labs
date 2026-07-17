"""Self-hosted Holo client — vendor-independent inference behind the same seam.

The whole point of this file is to remove Ghostpanel's #1 launch blocker: the
shared 5-10 requests/min rate limit on the *hosted* H-Company Holo API, plus the
hard dependency on that external vendor.

Key fact (verified in ``holo_client.py`` and CLAUDE.md): the Holo endpoint is
already **OpenAI-compatible**, and a self-hosted vLLM server running the SAME
weights (``Hcompany/Holo-3.1-35B-A3B``) emits coordinates on the SAME 0-1000
normalized grid. So ``LiveHoloClient`` works against a self-hosted endpoint
*unchanged* — you only have to point ``base_url`` at your vLLM ``/v1`` and give
it any (or empty) API key. See ``deploy/vllm/`` and ``docs/SELF_HOSTING.md``.

``SelfHostedHoloClient`` is a THIN subclass of ``LiveHoloClient`` that makes that
intent explicit and picks self-host-friendly defaults:

  * ``base_url`` defaults to a local vLLM endpoint (``http://localhost:8000/v1``).
  * ``model`` defaults to the HF repo id vLLM serves (``Hcompany/Holo-3.1-35B-A3B``).
  * ``api_key`` is optional (vLLM ignores it unless started with ``--api-key``);
    a placeholder is sent so the OpenAI SDK does not refuse to construct.
  * the rate limiter is effectively **disabled** — self-host has no vendor RPM
    cap, so throughput is bounded by your GPU, not a shared bucket. Pass an
    explicit ``rpm`` only if you deliberately want to throttle your own server.

It reuses ALL parsing / denormalization logic from ``LiveHoloClient`` (no code is
duplicated) and therefore satisfies the ``@runtime_checkable`` ``HoloClient``
Protocol just like its parent.
"""

from __future__ import annotations

from typing import Optional

from .holo_client import LiveHoloClient, RateLimiter

# Sensible defaults for a locally-served vLLM OpenAI-compatible endpoint.
DEFAULT_SELFHOST_BASE_URL = "http://localhost:8000/v1"
DEFAULT_SELFHOST_MODEL = "Hcompany/Holo-3.1-35B-A3B"
# No vendor cap on self-host: pick an RPM so high the shared token bucket never
# blocks. Real throughput is bounded by the GPU, not this number.
UNCAPPED_RPM = 1_000_000.0


class SelfHostedHoloClient(LiveHoloClient):
    """A ``HoloClient`` pointed at a self-hosted vLLM endpoint serving the Holo
    weights. Behaviourally identical to ``LiveHoloClient`` (same OpenAI-compatible
    calls, same 0-1000 -> pixel denormalization) with self-host defaults and no
    rate cap.
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = DEFAULT_SELFHOST_BASE_URL,
        model: str = DEFAULT_SELFHOST_MODEL,
        rpm: float = UNCAPPED_RPM,
        limiter: Optional[RateLimiter] = None,
        max_retries: int = 4,
    ) -> None:
        # vLLM accepts any token unless launched with --api-key; the OpenAI SDK
        # refuses to build with an empty key, so fall back to a harmless placeholder.
        super().__init__(
            api_key=api_key or "sk-selfhost-noauth",
            base_url=base_url or DEFAULT_SELFHOST_BASE_URL,
            model=model or DEFAULT_SELFHOST_MODEL,
            rpm=rpm,
            limiter=limiter,
            max_retries=max_retries,
        )
