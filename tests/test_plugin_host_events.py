"""Tests for plugin_loaded / plugin_unloaded event emission."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from device_connect_plugin_driver.plugin_host import PluginHostDriver

DEMO_MANIFEST = {
    "id": "demo",
    "entry_point": "capability.py",
    "class_name": "DemoCapability",
}

DEMO_CODE = """\
from device_connect_edge.drivers.decorators import rpc

class DemoCapability:
    def __init__(self, device=None):
        self.device = device

    @rpc()
    async def ping(self) -> dict:
        return {"pong": True}
"""


def _write_plugin(tmp_path: Path, plugin_id: str) -> None:
    cap_dir = tmp_path / plugin_id
    cap_dir.mkdir(parents=True)
    (cap_dir / "manifest.json").write_text(json.dumps({**DEMO_MANIFEST, "id": plugin_id}))
    (cap_dir / "capability.py").write_text(DEMO_CODE)


@pytest.mark.asyncio
async def test_emit_plugin_loaded_on_load(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "demo")
    host = PluginHostDriver(capabilities_dir=tmp_path, auto_load=False)
    host.plugin_loaded = AsyncMock()
    host.plugin_unloaded = AsyncMock()
    await host.connect()

    await host.load_plugin("demo")
    host.plugin_loaded.assert_awaited_once()
    call_kwargs = host.plugin_loaded.await_args.kwargs
    assert call_kwargs["plugin_id"] == "demo"
    assert "ping" in call_kwargs["functions"]


@pytest.mark.asyncio
async def test_emit_plugin_unloaded_on_unload(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "demo")
    host = PluginHostDriver(capabilities_dir=tmp_path, auto_load=False)
    host.plugin_loaded = AsyncMock()
    host.plugin_unloaded = AsyncMock()
    await host.connect()
    await host.load_plugin("demo")

    await host.unload_plugin("demo")
    host.plugin_unloaded.assert_awaited_once_with(plugin_id="demo")
