"""Storage backend factory. FROZEN signature (Agent P2-B implements)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import ArtifactStorage
from .local import LocalArtifactStorage
from .s3 import S3ArtifactStorage

if TYPE_CHECKING:
    from ghostpanel.server.config import Settings


def build_storage(settings: "Settings") -> ArtifactStorage:
    """Return the configured backend: 'local' -> LocalArtifactStorage(settings.artifact_dir),
    's3' -> S3ArtifactStorage(from settings.s3_*). Raise ValueError on unknown backend."""
    backend = settings.storage_backend
    if backend == "local":
        return LocalArtifactStorage(Path(settings.artifact_dir))
    if backend == "s3":
        return S3ArtifactStorage(
            settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            public_base_url=settings.s3_public_base_url,
        )
    raise ValueError(f"Unknown storage_backend: {backend!r}")


__all__ = ["build_storage"]
