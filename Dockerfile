# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Ghostpanel / Simulation Labs hosted backend.
#
# Base: Microsoft's official Playwright-for-Python image. It ships Chromium
# plus every system library Chromium needs (fonts, X libs, etc.) pre-installed,
# so the swarm's headless browser "just works" with no apt dance of our own.
#
# Tag: v1.55.0-jammy  (Playwright 1.55, Ubuntu 22.04 "jammy") — a real, current
# tag on mcr.microsoft.com/playwright/python. Our pyproject pins
# `playwright>=1.45`; pip may resolve a newer wheel than the browsers baked into
# the image, so we run `playwright install chromium` after the install to fetch
# the browser build that matches the installed Playwright version.
#
# One image, two roles:
#   * api    — default CMD: uvicorn serving ghostpanel.app:create_app
#   * worker — compose/fly override the command to `ghostpanel-worker`
# ---------------------------------------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GHOSTPANEL_HOST=0.0.0.0 \
    GHOSTPANEL_PORT=8000

WORKDIR /app

# --- Dependency layer (cache-friendly) -------------------------------------
# Copy only the build metadata first and install against a stub package tree so
# the heavy dependency layer is cached and only re-runs when pyproject changes,
# not on every source edit. setuptools finds packages under src/ and shared/
# (see pyproject [tool.setuptools.packages.find]), so we seed empty markers.
COPY pyproject.toml README.md ./
RUN mkdir -p src/ghostpanel shared/ghostpanel_contracts \
    && touch src/ghostpanel/__init__.py shared/ghostpanel_contracts/__init__.py \
    && pip install .

# --- Application layer ------------------------------------------------------
# Bring in the real source and reinstall the package only (deps already cached).
COPY . .
RUN pip install --no-deps .

# Ensure the Chromium build matches the pip-resolved Playwright version.
# System libraries are already present in the base image.
RUN playwright install chromium

EXPOSE 8000

# Default role: the API. The worker service overrides this with `ghostpanel-worker`.
CMD ["uvicorn", "--factory", "ghostpanel.app:create_app", "--host", "0.0.0.0", "--port", "8000"]
