"""Screenshot bytes -> tiny JPEG data URI for StepEvent.thumbnail_b64.

Every step's thumbnail travels over the WebSocket to the live grid, so keep it
small: downscale to ``max_w`` and JPEG-encode at modest quality.
"""

from __future__ import annotations

import base64
import io

from PIL import Image


def to_thumb_data_uri(png_bytes: bytes, max_w: int = 320) -> str:
    """Return ``data:image/jpeg;base64,...`` for a downscaled screenshot."""
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    if img.width > max_w:
        new_h = max(1, round(img.height * max_w / img.width))
        img = img.resize((max_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
