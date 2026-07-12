"""Console entrypoint — ``ghostpanel`` (see pyproject [project.scripts]).

Runs the composition-root app factory under uvicorn.
"""

from __future__ import annotations

import uvicorn

from .config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "ghostpanel.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
