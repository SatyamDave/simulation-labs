"""S3 / S3-compatible artifact storage. Implements the frozen ``ArtifactStorage``.

``boto3`` is imported lazily so merely importing this module never requires the
AWS SDK or any credentials. Keys are ``<run_id>/<rel_path>`` with forward slashes.
Works against AWS S3 or an S3-compatible endpoint (e.g. MinIO) via ``endpoint_url``.
"""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from typing import Optional

from .base import ArtifactStorage


class S3ArtifactStorage(ArtifactStorage):
    """Store run artifacts in an S3 (or S3-compatible) bucket."""

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str = "",
        region: str = "",
        public_base_url: str = "",
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url or ""
        self.region = region or ""
        self.public_base_url = (public_base_url or "").rstrip("/")
        self._client = None  # lazily built on first use

    def _get_client(self):
        """Build (and cache) the boto3 S3 client. Imports boto3 lazily."""
        if self._client is None:
            import boto3  # noqa: PLC0415 — lazy so import stays AWS-free

            kwargs = {}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            if self.region:
                kwargs["region_name"] = self.region
            self._client = boto3.client("s3", **kwargs)
        return self._client

    @staticmethod
    def _key(run_id: str, rel_path: str) -> str:
        rel = Path(rel_path.replace("\\", "/")).as_posix().lstrip("/")
        return f"{run_id}/{rel}"

    @staticmethod
    def _guess_content_type(name: str) -> str:
        ctype, _ = mimetypes.guess_type(name)
        return ctype or "application/octet-stream"

    def _upload_file(self, source: Path, key: str, content_type: str) -> None:
        self._get_client().upload_file(
            str(source), self.bucket, key,
            ExtraArgs={"ContentType": content_type},
        )

    def _upload_bytes(self, data: bytes, key: str, content_type: str) -> None:
        self._get_client().put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
        )

    async def put_file(self, run_id: str, rel_path: str, source: Path) -> str:
        source = Path(source)
        key = self._key(run_id, rel_path)
        content_type = self._guess_content_type(source.name)
        await asyncio.to_thread(self._upload_file, source, key, content_type)
        return self.url_for(run_id, rel_path)

    async def put_bytes(
        self,
        run_id: str,
        rel_path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        key = self._key(run_id, rel_path)
        await asyncio.to_thread(self._upload_bytes, data, key, content_type)
        return self.url_for(run_id, rel_path)

    def _upload_tree(self, run_id: str, source_dir: Path) -> None:
        source_dir = Path(source_dir)
        for path in source_dir.rglob("*"):
            if path.is_file():
                rel = path.relative_to(source_dir).as_posix()
                key = self._key(run_id, rel)
                self._upload_file(path, key, self._guess_content_type(path.name))

    async def put_dir(self, run_id: str, source_dir: Path) -> None:
        await asyncio.to_thread(self._upload_tree, run_id, Path(source_dir))

    def url_for(self, run_id: str, rel_path: str) -> str:
        rel = Path(rel_path.replace("\\", "/")).as_posix().lstrip("/")
        if self.public_base_url:
            return f"{self.public_base_url}/{run_id}/{rel}"
        key = f"{run_id}/{rel}"
        if self.endpoint_url:
            base = self.endpoint_url.rstrip("/")
            return f"{base}/{self.bucket}/{key}"
        if self.region and self.region != "us-east-1":
            return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"
        return f"https://{self.bucket}.s3.amazonaws.com/{key}"

    # --- authed read path ------------------------------------------------
    def _download(self, key: str) -> Optional[bytes]:
        from botocore.exceptions import ClientError  # noqa: PLC0415 — lazy

        try:
            resp = self._get_client().get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read()
        except ClientError:
            # NoSuchKey / access denied / missing object → treat as absent.
            return None

    async def read(self, run_id: str, rel_path: str) -> Optional[bytes]:
        key = self._key(run_id, rel_path)
        return await asyncio.to_thread(self._download, key)

    def presigned_url(
        self, run_id: str, rel_path: str, *, expires_s: int = 3600
    ) -> Optional[str]:
        key = self._key(run_id, rel_path)
        return self._get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_s,
        )


__all__ = ["S3ArtifactStorage"]
