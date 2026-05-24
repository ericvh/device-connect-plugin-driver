"""Tests for plugin validation CLI helper."""

from __future__ import annotations

from pathlib import Path

from device_connect_plugin_driver.plugin_validation import validate_plugin

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_validate_hello_world() -> None:
    result = validate_plugin(REPO_ROOT / "examples" / "hello-world")
    assert result.ok
    assert result.plugin_id == "hello-world"
    assert "hello_world" in result.rpc_methods


def test_validate_missing_manifest(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "bad-plugin"
    plugin_dir.mkdir()
    result = validate_plugin(plugin_dir)
    assert not result.ok
    assert any("manifest.json" in error for error in result.errors)
