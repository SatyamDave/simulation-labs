"""Turn raw PNG screenshot bytes into a small JPEG data URI for StepEvent.thumbnail_b64.

The thumbnail travels over the WebSocket on *every* step, so keep it small: downscale
to `max_w` px wide and JPEG-encode at moderate quality.
"""

from __future__ import annotations

import base64
import io

from PIL import Image


def to_thumb_data_uri(png_bytes: bytes, max_w: int = 320, quality: int = 60) -> str:
    """Downscale `png_bytes` to at most `max_w` wide and return a JPEG data URI.

    Returns an empty string if the input cannot be decoded (never raises), so a bad
    frame can't kill the run loop.
    """
    if not png_bytes:
        return ""
    try:
        img = Image.open(io.BytesIO(png_bytes))
        img.load()
        # JPEG has no alpha channel — flatten onto white.
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        if w > max_w:
            new_h = max(1, round(h * max_w / w))
            img = img.resize((max_w, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return ""
