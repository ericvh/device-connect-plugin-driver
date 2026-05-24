"""Plugin authoring templates and discoverable guide content for agents."""

from __future__ import annotations

import json
import os
import re
from importlib import resources
from pathlib import Path
from typing import Any

_TEMPLATE_DIR = "templates/plugin"

# Override with a public docs URL when published (GitHub, docs site, etc.)
DEFAULT_DOCS_BASE = os.environ.get(
    "DC_PLUGIN_DOCS_BASE_URL",
    "https://github.com/example/device-connect-plugin-driver",
)


def _plugin_id_to_class_name(plugin_id: str) -> str:
    parts = re.split(r"[-_]+", plugin_id.strip())
    return "".join(part[:1].upper() + part[1:] for part in parts if part) + "Capability"


def _render(text: str, *, plugin_id: str, class_name: str, description: str) -> str:
    return (
        text.replace("{{PLUGIN_ID}}", plugin_id)
        .replace("{{CLASS_NAME}}", class_name)
        .replace("{{DESCRIPTION}}", description)
    )


def _read_template(name: str) -> str:
    package = resources.files("device_connect_plugin_driver").joinpath(_TEMPLATE_DIR, name)
    return package.read_text(encoding="utf-8")


def build_plugin_template(
    *,
    plugin_id: str,
    class_name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Render manifest + capability source for a new plugin."""
    if not plugin_id or "/" in plugin_id or ".." in plugin_id:
        raise ValueError("plugin_id must be a simple name (e.g. garage-door)")

    resolved_class = class_name or _plugin_id_to_class_name(plugin_id)
    resolved_description = description or f"Capability plugin for {plugin_id}"

    manifest_raw = _read_template("manifest.json.tpl")
    capability_raw = _read_template("capability.py.tpl")
    readme_raw = _read_template("README.md")

    manifest_text = _render(
        manifest_raw,
        plugin_id=plugin_id,
        class_name=resolved_class,
        description=resolved_description,
    )
    capability_text = _render(
        capability_raw,
        plugin_id=plugin_id,
        class_name=resolved_class,
        description=resolved_description,
    )

    return {
        "plugin_id": plugin_id,
        "class_name": resolved_class,
        "description": resolved_description,
        "manifest": json.loads(manifest_text),
        "manifest_text": manifest_text,
        "capability_py": capability_text,
        "readme": _render(
            readme_raw,
            plugin_id=plugin_id,
            class_name=resolved_class,
            description=resolved_description,
        ),
        "layout": {
            f"{plugin_id}/manifest.json": "manifest_text",
            f"{plugin_id}/capability.py": "capability_py",
            f"{plugin_id}/README.md": "readme",
        },
        "packaging": {
            "command": f"tar -czf {plugin_id}.tgz -C . {plugin_id}",
            "note": "Archive the plugin folder; install via install_plugin_from_bundle or install_plugin_from_url",
        },
    }


def build_authoring_guide(*, docs_base: str | None = None) -> dict[str, Any]:
    """Structured authoring guide returned to agents via RPC."""
    base = (docs_base or DEFAULT_DOCS_BASE).rstrip("/")
    return {
        "version": "1",
        "device_type": "plugin_host",
        "summary": (
            "device-connect plugin_host devices extend their RPC surface by loading Python "
            "capability folders (manifest.json + capability.py). Agents scaffold with "
            "get_plugin_template, install with install_plugin_from_* RPCs, then invoke "
            "new functions on the same device credential."
        ),
        "discovery": {
            "authoring_rpc": "get_plugin_authoring_guide",
            "template_rpc": "get_plugin_template",
            "examples_rpc": "list_plugin_examples",
            "device_labels": {
                "plugin_driver:role": "plugin_host",
                "plugin_driver:authoring_rpc": "get_plugin_authoring_guide",
                "plugin_driver:template_rpc": "get_plugin_template",
            },
        },
        "docs": {
            "agents_playbook": f"{base}/blob/main/AGENTS.md",
            "readme": f"{base}/blob/main/README.md",
            "design": f"{base}/blob/main/DESIGN.md",
            "template_dir": f"{base}/tree/main/src/device_connect_plugin_driver/templates/plugin",
            "hello_world_example": f"{base}/tree/main/examples/hello-world",
            "delivery_manifests": f"{base}/tree/main/examples/plugin-manifests",
        },
        "workflow": [
            "Call get_plugin_authoring_guide (this RPC) or read AGENTS.md for conventions.",
            "Call get_plugin_template with plugin_id and optional class_name / description.",
            "Implement @rpc methods for the target service; add dependencies to manifest.json if needed.",
            "Package as .tar.gz: tar -czf PLUGIN.tgz -C parent PLUGIN/",
            "Install: install_plugin_from_bundle, install_plugin_from_url, or install_plugin_from_manifest.",
            "Confirm: list_plugins, get_device_functions (portal/agent-tools), invoke new RPCs.",
        ],
        "manifest_schema": {
            "required": ["id", "class_name", "entry_point"],
            "optional": ["version", "description", "dependencies"],
            "example": {
                "id": "my-service",
                "version": "0.1.0",
                "description": "Controls my service",
                "entry_point": "capability.py",
                "class_name": "MyServiceCapability",
                "dependencies": {"python": []},
            },
        },
        "install_methods": [
            {"rpc": "install_plugin_from_bundle", "when": "small archive, agent has base64"},
            {"rpc": "install_plugin_from_url", "when": "artifact hosted on HTTPS"},
            {"rpc": "install_plugin_from_docker", "when": "container sidecar with dc-plugin HTTP API"},
            {"rpc": "install_plugin_from_manifest", "when": "unified python or docker manifest"},
            {"rpc": "install_plugin", "when": "path already exists on device filesystem"},
            {"rpc": "publish_plugin_artifact", "when": "publish to local artifact store on host"},
            {"rpc": "get_plugin_artifact_url", "when": "resolve URL+digest for install_plugin_from_url"},
        ],
        "capability_conventions": {
            "constructor": "def __init__(self, device=None) — device is the host DeviceRuntime",
            "decorators": ["@rpc()", "@emit()", "@periodic(interval=seconds)"],
            "lifecycle": ["start()", "stop() optional async hooks"],
            "naming": "RPC names become mesh functions; use snake_case",
        },
    }


def list_plugin_examples(repo_examples_dir: Path | None = None) -> dict[str, Any]:
    """Describe bundled examples agents can copy or install."""
    examples = [
        {
            "id": "hello-world",
            "path": "examples/hello-world",
            "description": "Minimal single-RPC smoke test (hello_world)",
            "functions": ["hello_world"],
        },
        {
            "id": "demo",
            "path": "capabilities/demo",
            "description": "Bundled reference plugin (ping, echo)",
            "functions": ["ping", "echo"],
        },
        {
            "id": "plugin-template",
            "path": "src/device_connect_plugin_driver/templates/plugin",
            "description": "Scaffold with get_service_status + run_action stubs",
            "functions": ["get_service_status", "run_action"],
        },
    ]
    return {
        "status": "success",
        "examples": examples,
        "hint": "Use get_plugin_template to render the template for a specific service id",
        "repo_examples_dir": str(repo_examples_dir) if repo_examples_dir else None,
    }
