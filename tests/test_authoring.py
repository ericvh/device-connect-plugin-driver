"""Tests for plugin authoring guide and template RPCs."""

from __future__ import annotations

import json

import pytest

from device_connect_plugin_driver.authoring import build_authoring_guide, build_plugin_template
from device_connect_plugin_driver.plugin_host import PluginHostDriver


def test_build_plugin_template_renders_placeholders() -> None:
    result = build_plugin_template(
        plugin_id="garage-door",
        description="Opens the garage",
    )
    assert result["class_name"] == "GarageDoorCapability"
    assert result["manifest"]["id"] == "garage-door"
    assert "GarageDoorCapability" in result["capability_py"]
    assert "garage-door" in result["capability_py"]
    json.dumps(result["manifest"])


def test_build_authoring_guide_has_discovery() -> None:
    guide = build_authoring_guide()
    assert guide["discovery"]["authoring_rpc"] == "get_plugin_authoring_guide"
    assert "install_plugin_from_url" in {m["rpc"] for m in guide["install_methods"]}
    assert guide["docs"]["agents_playbook"].endswith("AGENTS.md")


@pytest.mark.asyncio
async def test_authoring_rpcs_on_host(tmp_path) -> None:
    host = PluginHostDriver(capabilities_dir=tmp_path, auto_load=False, enable_sidecars=False)
    await host.connect()

    guide = await host.get_plugin_authoring_guide()
    assert guide["status"] == "success"
    assert guide["discovery"]["template_rpc"] == "get_plugin_template"

    template = await host.get_plugin_template(
        plugin_id="pool-pump",
        description="Controls pool pump",
    )
    assert template["status"] == "success"
    assert template["class_name"] == "PoolPumpCapability"

    examples = await host.list_plugin_examples()
    assert examples["status"] == "success"
    assert any(ex["id"] == "hello-world" for ex in examples["examples"])

    status = await host.get_status()
    assert status["authoring"]["guide_rpc"] == "get_plugin_authoring_guide"


def test_plugin_host_labels() -> None:
    assert PluginHostDriver.labels["plugin_driver:authoring_rpc"] == "get_plugin_authoring_guide"
