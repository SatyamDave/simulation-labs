"""Local-disk artifact storage. Implements the frozen ``ArtifactStorage`` Protocol.

Files land under ``root/<run_id>/<rel_path>`` and are served back by the server at
``/artifacts/<run_id>/<rel_path>``. All blocking file IO runs in a worker thread
(``asyncio.to_thread``) so the async event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from .base import ArtifactStorage


class LocalArtifactStorage(ArtifactStorage):
    """Store run artifacts on the local filesystem under ``root``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _dest(self, run_id: str, rel_path: str) -> Path:
        """Absolute destination path for ``<run_id>/<rel_path>``."""
        rel = Path(rel_path.replace("\\", "/"))
        return self.root / run_id / rel

    def _write_bytes(self, dest: Path, data: bytes) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def _copy(self, source: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)

    async def put_file(self, run_id: str, rel_path: str, source: Path) -> str:
        dest = self._dest(run_id, rel_path)
        await asyncio.to_thread(self._copy, Path(source), dest)
        return self.url_for(run_id, rel_path)

    async def put_bytes(
        self,
        run_id: str,
        rel_path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        dest = self._dest(run_id, rel_path)
        await asyncio.to_thread(self._write_bytes, dest, data)
        return self.url_for(run_id, rel_path)

    def _copy_tree(self, run_id: str, source_dir: Path) -> None:
        source_dir = Path(source_dir)
        for path in source_dir.rglob("*"):
            if path.is_file():
                rel = path.relative_to(source_dir).as_posix()
                self._copy(path, self._dest(run_id, rel))

    async def put_dir(self, run_id: str, source_dir: Path) -> None:
        await asyncio.to_thread(self._copy_tree, run_id, Path(source_dir))

    def url_for(self, run_id: str, rel_path: str) -> str:
        rel = Path(rel_path.replace("\\", "/")).as_posix()
        return f"/artifacts/{run_id}/{rel}"


__all__ = ["LocalArtifactStorage"]
