"""Validate plugin directory layout before install or publish."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationIssue:
    level: str  # "error" | "warning"
    message: str


@dataclass
class ValidationResult:
    plugin_id: str | None = None
    path: str = ""
    ok: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: dict[str, Any] | None = None
    rpc_methods: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "plugin_id": self.plugin_id,
            "path": self.path,
            "errors": self.errors,
            "warnings": self.warnings,
            "rpc_methods": self.rpc_methods,
            "manifest": self.manifest,
        }


def _issue(result: ValidationResult, level: str, message: str) -> None:
    if level == "error":
        result.errors.append(message)
    else:
        result.warnings.append(message)


def validate_plugin(plugin_path: Path | str) -> ValidationResult:
    """Validate a plugin directory (manifest, entry point, class, @rpc methods)."""
    path = Path(plugin_path).expanduser().resolve()
    result = ValidationResult(path=str(path))

    if not path.is_dir():
        _issue(result, "error", f"not a directory: {path}")
        return result

    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        _issue(result, "error", "missing manifest.json")
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _issue(result, "error", f"invalid manifest.json: {exc}")
        return result

    if not isinstance(manifest, dict):
        _issue(result, "error", "manifest.json must be a JSON object")
        return result

    result.manifest = manifest
    plugin_id = manifest.get("id") or path.name
    result.plugin_id = plugin_id

    if not manifest.get("id"):
        _issue(result, "warning", "manifest missing id; using directory name")
    if not manifest.get("class_name"):
        _issue(result, "error", "manifest missing class_name")
    if not manifest.get("entry_point"):
        _issue(result, "error", "manifest missing entry_point")

    entry_point = manifest.get("entry_point", "capability.py")
    entry_file = path / entry_point
    if not entry_file.is_file():
        _issue(result, "error", f"entry point not found: {entry_file}")
        result.ok = len(result.errors) == 0
        return result

    class_name = manifest.get("class_name")
    if not class_name:
        result.ok = len(result.errors) == 0
        return result

    module_name = f"_dc_plugin_validate_{plugin_id.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, entry_file)
    if spec is None or spec.loader is None:
        _issue(result, "error", f"could not load module spec for {entry_file}")
        result.ok = len(result.errors) == 0
        return result

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        _issue(result, "error", f"failed to import entry point: {exc}")
        result.ok = len(result.errors) == 0
        return result
    finally:
        sys.modules.pop(module_name, None)

    cap_class = getattr(module, class_name, None)
    if cap_class is None:
        _issue(result, "error", f"class '{class_name}' not found in {entry_point}")
        result.ok = len(result.errors) == 0
        return result

    rpc_methods: list[str] = []
    for attr_name in dir(cap_class):
        if attr_name.startswith("_"):
            continue
        attr = getattr(cap_class, attr_name, None)
        if callable(attr) and getattr(attr, "_is_device_function", False):
            rpc_methods.append(attr_name)

    result.rpc_methods = sorted(rpc_methods)
    if not rpc_methods:
        _issue(result, "warning", "no @rpc methods found on capability class")

    deps = manifest.get("dependencies", {}).get("python", [])
    if deps:
        _issue(
            result,
            "warning",
            f"declares {len(deps)} python dependencies (install with DC_PLUGIN_INSTALL_DEPENDENCIES=1)",
        )

    result.ok = len(result.errors) == 0
    return result
