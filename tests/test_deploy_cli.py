"""Tests for deploy CLI helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from device_connect_plugin_driver.deploy_cli import pack_plugin_directory
from device_connect_plugin_driver.plugin_delivery import sha256_hex
from device_connect_plugin_driver.remote_client import parse_params_json

REPO_ROOT = Path(__file__).resolve().parents[1]
HELLO_WORLD = REPO_ROOT / "examples" / "hello-world"


def test_pack_plugin_directory() -> None:
    data = pack_plugin_directory(HELLO_WORLD)
    assert len(data) > 100
    assert sha256_hex(data)


def test_parse_params_json() -> None:
    assert parse_params_json('{"name": "agent"}') == {"name": "agent"}
    assert parse_params_json(None) == {}


def test_parse_params_json_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_params_json("[1]")


@pytest.mark.asyncio
async def test_deploy_install_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    from device_connect_plugin_driver.deploy_cli import _cmd_install

    class Args:
        host = "plugin-host-1"
        tenant = None
        credentials = None
        nats_url = None
        messaging_backend = None
        timeout = None
        json = True
        dry_run = True
        plugin_path = str(HELLO_WORLD)
        url = None
        digest = None
        plugin_id = None
        no_load = False
        skip_validate = False
        install_dependencies = False

    await _cmd_install(Args())
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "success"
    assert out["result"]["action"] == "install_plugin_from_bundle"
    assert out["result"]["plugin_id"] == "hello-world"
