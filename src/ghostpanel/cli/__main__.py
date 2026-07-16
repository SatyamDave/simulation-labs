"""`python -m ghostpanel.cli` entrypoint — mirrors the `sim` console script."""

from __future__ import annotations

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
