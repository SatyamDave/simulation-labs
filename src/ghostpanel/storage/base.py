"""Artifact storage abstraction. FROZEN protocol.

Runs produce artifacts (report.html, .webm videos, .wav audio, report.json,
heatmap PNG). The worker writes them through an ``ArtifactStorage`` so deployments
can keep them on local disk (dev) or an S3-compatible bucket (prod) without the
run code caring which. Keys are ``<run_id>/<relative path>``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class ArtifactStorage(Protocol):
    """Where run artifacts live. Implementations: LocalArtifactStorage, S3ArtifactStorage."""

    async def put_file(self, run_id: str, rel_path: str, source: Path) -> str:
        """Store a file already on local disk under ``<run_id>/<rel_path>``; return
        the retrievable URL (see ``url_for``)."""
        ...

    async def put_bytes(self, run_id: str, rel_path: str, data: bytes,
                        content_type: str = "application/octet-stream") -> str:
        """Store raw bytes under ``<run_id>/<rel_path>``; return the URL."""
        ...

    async def put_dir(self, run_id: str, source_dir: Path) -> None:
        """Recursively store every file under ``source_dir`` at ``<run_id>/<relpath>``.
        Used by the worker to publish the engine's per-run artifact directory."""
        ...

    def url_for(self, run_id: str, rel_path: str) -> str:
        """The URL a client uses to fetch the artifact. For local storage this is a
        server path like ``/artifacts/<run_id>/<rel_path>``; for S3 a bucket/CDN URL."""
        ...

    async def read(self, run_id: str, rel_path: str) -> Optional[bytes]:
        """Return the artifact's bytes, or None if it doesn't exist. Used by the
        authed artifact route to stream from local disk. Must reject path traversal
        (rel_path escaping the run dir) — return None rather than read outside."""
        ...

    def presigned_url(self, run_id: str, rel_path: str, *, expires_s: int = 3600) -> Optional[str]:
        """A short-lived direct URL (e.g. an S3 presigned GET) the client can fetch
        without hitting our server, or None when the backend can't presign (local) —
        in which case the caller streams via ``read``."""
        ...


__all__ = ["ArtifactStorage"]
