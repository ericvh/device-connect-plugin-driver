"""Fetch, verify, and extract plugin artifacts for the plugin host."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import aiohttp
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

ArchiveFormat = Literal["auto", "tar.gz", "tgz", "zip"]
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


class DockerPluginManifest(BaseModel):
    """Container plugin manifest — deploy as a sidecar proxied through the host."""

    id: str
    image: str
    digest: str | None = Field(
        default=None,
        description="Optional image digest pin (sha256:…)",
    )
    port: int = 8787
    env: dict[str, str] = Field(default_factory=dict)
    pull: bool = True
    type: Literal["docker"] = "docker"

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value or "/" in value or ".." in value:
            raise ValueError("plugin id must be a simple name")
        return value


@dataclass(frozen=True)
class DeliveryConfig:
    max_bytes: int
    url_allowlist: tuple[str, ...]
    require_digest: bool

    @classmethod
    def from_env(cls) -> DeliveryConfig:
        allowlist = tuple(
            part.strip().lower()
            for part in os.environ.get("DC_PLUGIN_INSTALL_URL_ALLOWLIST", "").split(",")
            if part.strip()
        )
        require_digest = os.environ.get("DC_PLUGIN_INSTALL_REQUIRE_DIGEST", "").lower() in {
            "1",
            "true",
            "yes",
        }
        max_bytes = int(os.environ.get("DC_PLUGIN_MAX_PLUGIN_BYTES", str(DEFAULT_MAX_BYTES)))
        return cls(max_bytes=max_bytes, url_allowlist=allowlist, require_digest=require_digest)


def normalize_digest(digest: str | None) -> str | None:
    if not digest:
        return None
    value = digest.strip().lower()
    if value.startswith("sha256:"):
        value = value[7:]
    return value


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_digest(data: bytes, digest: str | None, *, require: bool = False) -> None:
    normalized = normalize_digest(digest)
    if normalized is None:
        if require:
            raise ValueError("digest is required (set DC_PLUGIN_INSTALL_REQUIRE_DIGEST=1 or pass digest=)")
        return
    if sha256_hex(data) != normalized:
        raise ValueError("digest mismatch")


def _check_url_allowed(url: str, allowlist: tuple[str, ...]) -> None:
    if not allowlist:
        return
    host = urlparse(url).hostname
    if host is None:
        raise ValueError(f"invalid URL: {url}")
    host = host.lower()
    if host not in allowlist and not any(host.endswith(f".{allowed}") for allowed in allowlist):
        raise ValueError(f"URL host '{host}' is not in DC_PLUGIN_INSTALL_URL_ALLOWLIST")


async def fetch_url(
    url: str,
    *,
    config: DeliveryConfig,
    session: aiohttp.ClientSession | None = None,
) -> bytes:
    _check_url_allowed(url, config.url_allowlist)
    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            resp.raise_for_status()
            if resp.content_length is not None and resp.content_length > config.max_bytes:
                raise ValueError(f"artifact exceeds max size ({config.max_bytes} bytes)")
            chunks: list[bytes] = []
            size = 0
            async for chunk in resp.content.iter_chunked(64 * 1024):
                size += len(chunk)
                if size > config.max_bytes:
                    raise ValueError(f"artifact exceeds max size ({config.max_bytes} bytes)")
                chunks.append(chunk)
            return b"".join(chunks)
    finally:
        if owns_session and session is not None:
            await session.close()


def decode_bundle(bundle_b64: str, *, max_bytes: int) -> bytes:
    try:
        data = base64.b64decode(bundle_b64, validate=True)
    except Exception as exc:
        raise ValueError("invalid base64 bundle") from exc
    if len(data) > max_bytes:
        raise ValueError(f"bundle exceeds max size ({max_bytes} bytes)")
    return data


def detect_archive_format(data: bytes, fmt: ArchiveFormat, filename: str | None = None) -> ArchiveFormat:
    if fmt != "auto":
        return fmt
    name = (filename or "").lower()
    if name.endswith(".zip"):
        return "zip"
    if name.endswith((".tar.gz", ".tgz")):
        return "tar.gz"
    if data[:2] == b"PK":
        return "zip"
    return "tar.gz"


def _find_plugin_root(extracted_dir: Path) -> Path:
    if (extracted_dir / "manifest.json").is_file():
        return extracted_dir
    children = [p for p in extracted_dir.iterdir() if p.is_dir()]
    if len(children) == 1 and (children[0] / "manifest.json").is_file():
        return children[0]
    raise ValueError("archive must contain manifest.json at root or in a single top-level folder")


def _safe_extract_tar(archive: tarfile.TarFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in archive.getmembers():
        member_path = (dest / member.name).resolve()
        if not str(member_path).startswith(str(dest)):
            raise ValueError(f"unsafe path in archive: {member.name}")
    if hasattr(tarfile, "data_filter"):
        archive.extractall(dest, filter="data")
    else:
        archive.extractall(dest)


def _safe_extract_zip(archive: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for name in archive.namelist():
        member_path = (dest / name).resolve()
        if not str(member_path).startswith(str(dest)):
            raise ValueError(f"unsafe path in archive: {name}")
    archive.extractall(dest)


def extract_plugin_archive(
    data: bytes,
    *,
    dest_parent: Path,
    plugin_id: str | None,
    archive_format: ArchiveFormat = "auto",
    filename: str | None = None,
) -> tuple[str, Path]:
    """Extract archive bytes into dest_parent and return (plugin_id, plugin_dir)."""
    dest_parent.mkdir(parents=True, exist_ok=True)
    fmt = detect_archive_format(data, archive_format, filename)
    staging = dest_parent / f".staging-{plugin_id or 'plugin'}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        if fmt == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                _safe_extract_zip(archive, staging)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                _safe_extract_tar(archive, staging)

        plugin_root = _find_plugin_root(staging)
        manifest = json.loads((plugin_root / "manifest.json").read_text(encoding="utf-8"))
        resolved_id = plugin_id or manifest.get("id") or plugin_root.name
        if not resolved_id or "/" in resolved_id or ".." in resolved_id:
            raise ValueError("invalid plugin id")

        final_dir = dest_parent / resolved_id
        if final_dir.exists():
            shutil.rmtree(final_dir)
        if plugin_root == staging:
            staging.rename(final_dir)
        else:
            shutil.move(str(plugin_root), str(final_dir))
            shutil.rmtree(staging, ignore_errors=True)
        return resolved_id, final_dir
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def parse_docker_manifest(raw: dict[str, Any] | str) -> DockerPluginManifest:
    if isinstance(raw, str):
        raw = json.loads(raw)
    return DockerPluginManifest.model_validate(raw)
