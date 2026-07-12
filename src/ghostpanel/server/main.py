"""Ghostpanel server entrypoint — the `ghostpanel` console script.

Run:  ghostpanel        (or)  python -m ghostpanel.server.main
"""

from __future__ import annotations

import logging

import uvicorn

from ghostpanel.server.config import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    uvicorn.run(
        "ghostpanel.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
