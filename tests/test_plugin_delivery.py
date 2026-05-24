"""Tests for plugin delivery helpers and install RPCs."""

from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path

import pytest
from aiohttp import web

from device_connect_plugin_driver.plugin_delivery import (
    DeliveryConfig,
    decode_bundle,
    extract_plugin_archive,
    sha256_hex,
    verify_digest,
)
from device_connect_plugin_driver.plugin_host import PluginHostDriver

REPO_ROOT = Path(__file__).resolve().parents[1]
HELLO_WORLD = REPO_ROOT / "examples" / "hello-world"


def _pack_plugin(source: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        archive.add(source, arcname=source.name)
    return buf.getvalue()


@pytest.fixture
def hello_archive() -> bytes:
    return _pack_plugin(HELLO_WORLD)


def test_verify_digest_accepts_sha256_prefix(hello_archive: bytes) -> None:
    digest = f"sha256:{sha256_hex(hello_archive)}"
    verify_digest(hello_archive, digest)


def test_verify_digest_rejects_mismatch(hello_archive: bytes) -> None:
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_digest(hello_archive, "sha256:" + "0" * 64)


def test_extract_plugin_archive(hello_archive: bytes, tmp_path: Path) -> None:
    plugin_id, dest = extract_plugin_archive(
        hello_archive,
        dest_parent=tmp_path,
        plugin_id=None,
    )
    assert plugin_id == "hello-world"
    assert (dest / "manifest.json").is_file()
    assert (dest / "capability.py").is_file()


@pytest.mark.asyncio
async def test_install_plugin_from_bundle(hello_archive: bytes, tmp_path: Path) -> None:
    host = PluginHostDriver(
        capabilities_dir=tmp_path,
        auto_load=False,
        enable_sidecars=False,
    )
    await host.connect()
    digest = f"sha256:{sha256_hex(hello_archive)}"
    result = await host.install_plugin_from_bundle(
        bundle_b64=base64.b64encode(hello_archive).decode("ascii"),
        digest=digest,
    )
    assert result["status"] == "success"
    assert result["plugin_id"] == "hello-world"
    assert await host.invoke("hello_world", name="bundle") == {"message": "Hello, bundle!"}


@pytest.mark.asyncio
async def test_install_plugin_from_url(hello_archive: bytes, tmp_path: Path) -> None:
    app = web.Application()

    async def handler(_request: web.Request) -> web.Response:
        return web.Response(body=hello_archive, content_type="application/gzip")

    app.router.add_get("/hello-world.tgz", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
    url = f"http://127.0.0.1:{port}/hello-world.tgz"

    host = PluginHostDriver(
        capabilities_dir=tmp_path,
        auto_load=False,
        enable_sidecars=False,
    )
    host._delivery_config = DeliveryConfig(max_bytes=10_000_000, url_allowlist=(), require_digest=False)
    await host.connect()

    result = await host.install_plugin_from_url(url=url, digest=f"sha256:{sha256_hex(hello_archive)}")
    assert result["status"] == "success"
    assert await host.invoke("hello_world") == {"message": "Hello, world!"}

    await runner.cleanup()


@pytest.mark.asyncio
async def test_install_plugin_from_manifest_python_url(hello_archive: bytes, tmp_path: Path) -> None:
    host = PluginHostDriver(capabilities_dir=tmp_path, auto_load=False, enable_sidecars=False)
    await host.connect()
    result = await host.install_plugin_from_manifest(
        {
            "type": "python",
            "bundle_b64": base64.b64encode(hello_archive).decode("ascii"),
            "digest": f"sha256:{sha256_hex(hello_archive)}",
        }
    )
    assert result["status"] == "success"
    assert result["plugin_id"] == "hello-world"


def test_decode_bundle_rejects_oversize() -> None:
    tiny = DeliveryConfig(max_bytes=8, url_allowlist=(), require_digest=False)
    with pytest.raises(ValueError, match="exceeds max size"):
        decode_bundle(base64.b64encode(b"x" * 16).decode("ascii"), max_bytes=tiny.max_bytes)
