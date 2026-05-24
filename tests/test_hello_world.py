"""Smoke tests for the hello-world example plugin."""

from __future__ import annotations

from pathlib import Path

import pytest

from device_connect_plugin_driver.plugin_host import PluginHostDriver

REPO_ROOT = Path(__file__).resolve().parents[1]
HELLO_WORLD = REPO_ROOT / "examples" / "hello-world"


@pytest.mark.asyncio
async def test_install_and_invoke_hello_world(tmp_path: Path) -> None:
    host = PluginHostDriver(
        capabilities_dir=tmp_path,
        auto_load=False,
        enable_sidecars=False,
    )
    await host.connect()

    result = await host.install_plugin(str(HELLO_WORLD))
    assert result["status"] in {"success", "partial"}
    assert result["plugin_id"] == "hello-world"

    greeting = await host.invoke("hello_world", name="plugin")
    assert greeting == {"message": "Hello, plugin!"}

    default = await host.invoke("hello_world")
    assert default == {"message": "Hello, world!"}

    listing = await host.list_plugins()
    assert "hello-world" in listing["loaded"]
