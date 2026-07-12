"""Live Holo smoke test — only runs when HAI_API_KEY is set. Skipped in CI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ghostpanel.engine.holo_client import LiveHoloClient

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "sample_screenshot.png"


@pytest.mark.skipif(
    not os.getenv("HAI_API_KEY"),
    reason="HAI_API_KEY not set; live Holo smoke test skipped",
)
@pytest.mark.asyncio
async def test_live_localize_returns_plausible_coords():
    client = LiveHoloClient(
        api_key=os.environ["HAI_API_KEY"],
        base_url=os.getenv("HAI_BASE_URL", "https://api.hcompany.ai/v1/"),
        model=os.getenv("HAI_MODEL", "holo3-1-35b-a3b"),
        rpm=float(os.getenv("HAI_RPM", "10")),
    )
    png = FIXTURE.read_bytes()
    x, y = await client.localize(png, "the primary button")
    from PIL import Image
    import io

    w, h = Image.open(io.BytesIO(png)).size
    assert 0 <= x < w and 0 <= y < h
