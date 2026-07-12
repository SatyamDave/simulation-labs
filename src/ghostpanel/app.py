"""Ghostpanel composition root — create_app() FastAPI factory.

Wires Settings, WebSocketHub, RunRegistry and SwarmManager together, launches
the ONE shared Playwright browser in the lifespan, and mounts the API router,
the artifact dir and (if built) the frontend.

Everything is injectable so tests construct the app with fakes and no real
browser: pass `swarm=` (or `launch_browser=False`) and your own Settings.
Playwright is imported lazily inside the lifespan — importing this module
never pulls in engine/runner/voice/report code.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ghostpanel.server.api import router
from ghostpanel.server.config import Settings
from ghostpanel.server.runs import RunRegistry
from ghostpanel.server.swarm import SwarmManager
from ghostpanel.server.ws import WebSocketHub

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WEB_DIST = _REPO_ROOT / "web" / "dist"


def create_app(
    settings: Optional[Settings] = None,
    *,
    swarm: Optional[SwarmManager] = None,
    launch_browser: Optional[bool] = None,
) -> FastAPI:
    """Build the Ghostpanel app.

    - Production (`ghostpanel` script): no args — Settings from .env, real
      SwarmManager with the concrete registry classes (lazy imports inside
      SwarmManager's default factories), Chromium launched on startup.
    - Tests: pass a pre-wired SwarmManager (stub factories) and/or
      launch_browser=False; the app then never touches Playwright.
    """
    settings = settings or Settings.from_env()
    hub = WebSocketHub()
    registry = RunRegistry()
    swarm = swarm or SwarmManager(settings, hub, registry)
    # An injected swarm brings its own hub/registry — the routes must see those.
    hub = swarm.hub
    registry = swarm.registry
    want_browser = launch_browser if launch_browser is not None else True

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        playwright = None
        browser = None
        if want_browser and swarm.browser is None:
            from playwright.async_api import async_playwright  # lazy: not needed in tests

            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
            swarm.browser = browser
            logger.info("Playwright Chromium launched (shared by the swarm)")
        try:
            yield
        finally:
            await swarm.shutdown()
            if browser is not None:
                await browser.close()
                swarm.browser = None
            if playwright is not None:
                await playwright.stop()

    app = FastAPI(title="Ghostpanel", lifespan=lifespan)
    app.state.settings = settings
    app.state.hub = hub
    app.state.registry = registry
    app.state.swarm = swarm

    # Permissive CORS for local dev (Vite frontend on another port).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    # Artifacts: video receipts, exit-interview .wav, report HTML.
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/artifacts",
        StaticFiles(directory=str(settings.artifact_dir), check_dir=False),
        name="artifacts",
    )

    # Built frontend at / (mounted last so API routes win).
    if _WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")

    return app
