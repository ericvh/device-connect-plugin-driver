"""Local plugin artifact store with optional HTTP serving for install_plugin_from_url."""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiohttp import web

from device_connect_plugin_driver.plugin_delivery import sha256_hex

logger = logging.getLogger(__name__)

METADATA_NAME = "artifact.json"


@dataclass(frozen=True)
class ArtifactStoreConfig:
    artifact_dir: Path
    serve_host: str
    serve_port: int
    public_base_url: str | None

    @classmethod
    def from_env(cls, *, capabilities_dir: Path) -> ArtifactStoreConfig:
        artifact_dir = Path(
            os.environ.get("DC_PLUGIN_ARTIFACT_DIR", str(capabilities_dir / ".artifacts"))
        ).expanduser()
        serve_host = os.environ.get("DC_PLUGIN_ARTIFACT_HOST", "127.0.0.1")
        serve_port = int(os.environ.get("DC_PLUGIN_ARTIFACT_PORT", "8790"))
        public_base = os.environ.get("DC_PLUGIN_ARTIFACT_PUBLIC_URL") or None
        return cls(
            artifact_dir=artifact_dir,
            serve_host=serve_host,
            serve_port=serve_port,
            public_base_url=public_base,
        )


@dataclass
class ArtifactRecord:
    plugin_id: str
    filename: str
    digest: str
    size: int
    version: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "filename": self.filename,
            "digest": f"sha256:{self.digest}",
            "size": self.size,
            "version": self.version,
            "created_at": self.created_at,
        }


class ArtifactStore:
    """Store plugin archives on disk for local or portal-adjacent hosting."""

    def __init__(self, config: ArtifactStoreConfig) -> None:
        self._config = config
        self._config.artifact_dir.mkdir(parents=True, exist_ok=True)

    @property
    def artifact_dir(self) -> Path:
        return self._config.artifact_dir

    def _plugin_dir(self, plugin_id: str) -> Path:
        return self._config.artifact_dir / plugin_id

    def _artifact_url(self, plugin_id: str, filename: str) -> str:
        if self._config.public_base_url:
            base = self._config.public_base_url.rstrip("/")
            return f"{base}/artifacts/{plugin_id}/{filename}"
        return (
            f"http://{self._config.serve_host}:{self._config.serve_port}"
            f"/artifacts/{plugin_id}/{filename}"
        )

    def pack_plugin_dir(self, plugin_dir: Path) -> bytes:
        plugin_dir = plugin_dir.resolve()
        if not (plugin_dir / "manifest.json").is_file():
            raise ValueError(f"missing manifest.json in {plugin_dir}")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as archive:
            archive.add(plugin_dir, arcname=plugin_dir.name)
        return buf.getvalue()

    def publish(
        self,
        data: bytes,
        *,
        plugin_id: str,
        version: str | None = None,
    ) -> ArtifactRecord:
        digest = sha256_hex(data)
        plugin_store = self._plugin_dir(plugin_id)
        plugin_store.mkdir(parents=True, exist_ok=True)
        filename = f"{version}.tgz" if version else f"{digest[:12]}.tgz"
        artifact_path = plugin_store / filename
        artifact_path.write_bytes(data)
        record = ArtifactRecord(
            plugin_id=plugin_id,
            filename=filename,
            digest=digest,
            size=len(data),
            version=version,
            created_at=datetime.now(UTC).isoformat(),
        )
        (plugin_store / METADATA_NAME).write_text(
            json.dumps(record.to_dict(), indent=2),
            encoding="utf-8",
        )
        logger.info("Published artifact %s/%s (%d bytes)", plugin_id, filename, len(data))
        return record

    def publish_plugin_dir(
        self,
        plugin_dir: Path,
        *,
        plugin_id: str | None = None,
        version: str | None = None,
    ) -> ArtifactRecord:
        plugin_dir = plugin_dir.resolve()
        manifest = json.loads((plugin_dir / "manifest.json").read_text(encoding="utf-8"))
        resolved_id = plugin_id or manifest.get("id") or plugin_dir.name
        version = version or manifest.get("version")
        data = self.pack_plugin_dir(plugin_dir)
        return self.publish(data, plugin_id=resolved_id, version=version)

    def list_artifacts(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if not self._config.artifact_dir.is_dir():
            return records
        for plugin_dir in sorted(self._config.artifact_dir.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue
            meta_path = plugin_dir / METADATA_NAME
            if meta_path.is_file():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["url"] = self._artifact_url(meta["plugin_id"], meta["filename"])
                records.append(meta)
                continue
            for artifact_file in sorted(plugin_dir.glob("*.tgz")):
                data = artifact_file.read_bytes()
                records.append(
                    {
                        "plugin_id": plugin_dir.name,
                        "filename": artifact_file.name,
                        "digest": f"sha256:{sha256_hex(data)}",
                        "size": len(data),
                        "url": self._artifact_url(plugin_dir.name, artifact_file.name),
                    }
                )
        return records

    def get_artifact(self, plugin_id: str, *, version: str | None = None) -> dict[str, Any] | None:
        plugin_store = self._plugin_dir(plugin_id)
        if not plugin_store.is_dir():
            return None
        if version:
            candidate = plugin_store / f"{version}.tgz"
            if candidate.is_file():
                data = candidate.read_bytes()
                return {
                    "plugin_id": plugin_id,
                    "filename": candidate.name,
                    "digest": f"sha256:{sha256_hex(data)}",
                    "size": len(data),
                    "version": version,
                    "url": self._artifact_url(plugin_id, candidate.name),
                }
            return None
        meta_path = plugin_store / METADATA_NAME
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["url"] = self._artifact_url(plugin_id, meta["filename"])
            return meta
        tgz_files = sorted(plugin_store.glob("*.tgz"))
        if not tgz_files:
            return None
        latest = tgz_files[-1]
        data = latest.read_bytes()
        return {
            "plugin_id": plugin_id,
            "filename": latest.name,
            "digest": f"sha256:{sha256_hex(data)}",
            "size": len(data),
            "url": self._artifact_url(plugin_id, latest.name),
        }

    def remove(self, plugin_id: str) -> bool:
        plugin_store = self._plugin_dir(plugin_id)
        if not plugin_store.is_dir():
            return False
        shutil.rmtree(plugin_store)
        return True


class ArtifactServer:
    """Minimal HTTP server for artifact downloads."""

    def __init__(self, store: ArtifactStore, *, host: str, port: int) -> None:
        self._store = store
        self._host = host
        self._port = port
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    async def start(self) -> None:
        if self._runner is not None:
            return

        async def list_handler(_request: web.Request) -> web.Response:
            return web.json_response({"artifacts": self._store.list_artifacts()})

        async def artifact_handler(request: web.Request) -> web.Response:
            plugin_id = request.match_info["plugin_id"]
            filename = request.match_info["filename"]
            path = self._store.artifact_dir / plugin_id / filename
            if not path.is_file():
                raise web.HTTPNotFound()
            return web.FileResponse(path)

        app = web.Application()
        app.router.add_get("/artifacts", list_handler)
        app.router.add_get("/artifacts/{plugin_id}/{filename}", artifact_handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        logger.info("Artifact server listening on %s", self.base_url)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
