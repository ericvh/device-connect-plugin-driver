"""Tests for the Device Connect plugin host driver."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from device_connect_plugin_driver.plugin_host import PluginHostDriver

DEMO_MANIFEST = {
    "id": "demo",
    "entry_point": "capability.py",
    "class_name": "DemoCapability",
}

DEMO_CODE = '''\
from device_connect_edge.drivers.decorators import rpc

class DemoCapability:
    def __init__(self, device=None):
        self.device = device

    @rpc()
    async def ping(self) -> dict:
        return {"pong": True}
'''


def _write_plugin(tmp_path: Path, plugin_id: str, code: str = DEMO_CODE) -> Path:
    cap_dir = tmp_path / plugin_id
    cap_dir.mkdir(parents=True)
    (cap_dir / "manifest.json").write_text(json.dumps({**DEMO_MANIFEST, "id": plugin_id}))
    (cap_dir / "capability.py").write_text(code)
    return cap_dir


@pytest.fixture
def host(tmp_path: Path) -> PluginHostDriver:
    return PluginHostDriver(
        capabilities_dir=tmp_path,
        auto_load=False,
        enable_sidecars=False,
    )


@pytest.mark.asyncio
async def test_load_and_invoke_plugin(host: PluginHostDriver, tmp_path: Path) -> None:
    _write_plugin(tmp_path, "demo")
    await host.connect()
    result = await host.load_plugin("demo")
    assert result["status"] == "success"
    assert await host.invoke("ping") == {"pong": True}


@pytest.mark.asyncio
async def test_list_plugins(host: PluginHostDriver, tmp_path: Path) -> None:
    _write_plugin(tmp_path, "demo")
    await host.connect()
    listing = await host.list_plugins()
    assert listing["status"] == "success"
    assert len(listing["available"]) == 1
    assert listing["available"][0]["id"] == "demo"


@pytest.mark.asyncio
async def test_refresh_mesh_infra(host: PluginHostDriver) -> None:
    runtime = MagicMock()
    runtime._d2d_mode = False
    runtime._register = AsyncMock()
    host._device = runtime
    await host._refresh_mesh_advertisement()
    runtime._register.assert_awaited_once_with(force=True)


@pytest.mark.asyncio
async def test_refresh_mesh_d2d(host: PluginHostDriver) -> None:
    runtime = MagicMock()
    runtime._d2d_mode = True
    announcer = MagicMock()
    runtime._d2d_announcer = announcer
    host._device = runtime
    await host._refresh_mesh_advertisement()
    announcer.trigger_burst.assert_called_once()
