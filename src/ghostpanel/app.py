"""Composition root — the ONLY module that imports concrete classes from every
other Ghostpanel module and wires them into a running FastAPI app.

``create_app()`` builds the app; on startup it launches ONE shared Chromium
``Browser`` and one shared rate-limited ``LiveHoloClient`` (a single
``RateLimiter`` shared by the whole swarm), constructs the ``SwarmManager``, and
mounts the artifact store + the built frontend. On shutdown it closes the browser
and Playwright.

Test seams (kept minimal, all keyword-only, never used by the ``factory=True``
entrypoint which calls ``create_app()`` with no args):
  * ``holo_client``   — inject a ``FakeHoloClient`` so tests need no network.
  * ``enable_voice``  — disable Gradium/Anthropic so tests stay offline.
  * ``launch_browser``— skip the real browser (construction-only smoke tests).
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import gradium

from ghostpanel.engine.holo_client import LiveHoloClient
from ghostpanel.runner.policy import RequestPolicy
from ghostpanel.voice.gradium_voice import GradiumVoiceEngine
from ghostpanel.voice.voices import assign_voices
from ghostpanel_contracts import PersonaConfig

from .server.api import router
from .server.config import Settings, get_settings
from .server.runs import RunRegistry
from .server.swarm import SwarmManager
from .server.ws import WebSocketHub

# web/dist lives at the repo root: src/ghostpanel/app.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WEB_DIST = _REPO_ROOT / "web" / "dist"


def create_app(
    *,
    settings: Optional[Settings] = None,
    holo_client: Optional[Any] = None,
    enable_voice: Optional[bool] = None,
    launch_browser: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    if enable_voice is None:
        enable_voice = settings.has_gradium

    artifact_dir = Path(settings.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # NemoClaw browse-only mirror: parse the configured OpenShell preset once
    # and hand it to every session runner. Loud failure on a bad file — a
    # misconfigured security policy must never silently no-op.
    request_policy: Optional[RequestPolicy] = None
    if settings.nemoclaw_policy_file is not None:
        request_policy = RequestPolicy.from_file(settings.nemoclaw_policy_file)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN202
        # --- startup: launch the shared browser + build the swarm ---
        browser = None
        if launch_browser:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True)
            app.state._playwright = pw
            app.state.browser = browser

        holo = holo_client
        if holo is None:
            holo = LiveHoloClient(
                api_key=settings.hai_api_key,
                base_url=settings.holo_base_url,
                model=settings.hai_model,
                rpm=settings.hai_rpm,
            )

        voice_factory = None
        voice_assigner = None
        anthropic_key: Optional[str] = None
        if enable_voice:
            anthropic_key = settings.anthropic_api_key or None
            if settings.has_gradium:
                def voice_factory(run_dir: Path) -> GradiumVoiceEngine:  # noqa: ANN202
                    return GradiumVoiceEngine(
                        api_key=settings.gradium_api_key,
                        artifact_dir=run_dir,
                        anthropic_key=anthropic_key,
                    )

                async def voice_assigner(
                    personas: list[PersonaConfig],
                ) -> dict[str, str]:
                    # One catalog lookup per run: distinct Gradium preset/cloned
                    # voices per persona. SwarmManager guards every failure and
                    # never overrides an explicit persona voice_id.
                    client = gradium.GradiumClient(api_key=settings.gradium_api_key)
                    return await assign_voices(personas, client)

        app.state.swarm = SwarmManager(
            browser=browser,
            holo_client=holo,
            hub=hub,
            registry=registry,
            artifact_dir=artifact_dir,
            anthropic_key=anthropic_key,
            voice_engine_factory=voice_factory,
            voice_assigner=voice_assigner,
            request_policy=request_policy,
        )

        try:
            yield
        finally:
            # --- shutdown: close the browser + Playwright ---
            if app.state.browser is not None:
                with contextlib.suppress(Exception):
                    await app.state.browser.close()
            if app.state._playwright is not None:
                with contextlib.suppress(Exception):
                    await app.state._playwright.stop()

    app = FastAPI(title="Ghostpanel Orchestrator", lifespan=lifespan)

    # Permissive CORS for local dev (frontend runs on a separate Vite port).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Shared, browser-independent state is safe to build now.
    hub = WebSocketHub()
    registry = RunRegistry()
    app.state.settings = settings
    app.state.hub = hub
    app.state.runs = registry
    app.state.swarm = None
    app.state.browser = None
    app.state._playwright = None

    # API routes first so they win over the catch-all "/" mount below.
    app.include_router(router)

    # Serve artifacts (.webm / .wav / report.html) from the artifact dir.
    app.mount(
        "/artifacts",
        StaticFiles(directory=str(artifact_dir), check_dir=False),
        name="artifacts",
    )

    # Mount the built frontend at "/" if present (registered last: catch-all).
    if _WEB_DIST.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(_WEB_DIST), html=True, check_dir=False),
            name="web",
        )

    return app
