"""Opt-in sandboxed pip install for plugin manifest dependencies."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DependencyInstallConfig:
    enabled: bool
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> DependencyInstallConfig:
        enabled = os.environ.get("DC_PLUGIN_INSTALL_DEPENDENCIES", "").lower() in {
            "1",
            "true",
            "yes",
        }
        timeout = int(os.environ.get("DC_PLUGIN_INSTALL_DEPENDENCIES_TIMEOUT", "120"))
        return cls(enabled=enabled, timeout_seconds=timeout)


def plugin_deps_dir(capabilities_dir: Path, plugin_id: str) -> Path:
    """Per-plugin sandbox directory for pip --target installs."""
    return capabilities_dir / ".deps" / plugin_id


def plugin_site_packages(capabilities_dir: Path, plugin_id: str) -> Path:
    """Site-packages path inside the plugin dependency sandbox."""
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return plugin_deps_dir(capabilities_dir, plugin_id) / "lib" / f"python{version}" / "site-packages"


def read_manifest_deps(plugin_dir: Path) -> list[str]:
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    deps = manifest.get("dependencies", {}).get("python", [])
    return [str(dep) for dep in deps]


def install_plugin_dependencies(
    plugin_dir: Path,
    *,
    capabilities_dir: Path,
    plugin_id: str | None = None,
    config: DependencyInstallConfig | None = None,
) -> dict[str, object]:
    """Install manifest python dependencies into a per-plugin sandbox.

    Returns a result dict with status and installed package specs.
    """
    cfg = config or DependencyInstallConfig.from_env()
    if not cfg.enabled:
        return {"status": "skipped", "reason": "DC_PLUGIN_INSTALL_DEPENDENCIES not enabled"}

    deps = read_manifest_deps(plugin_dir)
    if not deps:
        return {"status": "skipped", "reason": "no python dependencies declared"}

    resolved_id = plugin_id or json.loads((plugin_dir / "manifest.json").read_text())["id"]
    target = plugin_site_packages(capabilities_dir, resolved_id)
    target.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--target",
        str(target),
        "--upgrade",
        *deps,
    ]
    logger.info("Installing dependencies for %s: %s", resolved_id, deps)
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=cfg.timeout_seconds,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"pip install failed for {resolved_id}: {stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"pip install timed out for {resolved_id}") from exc

    return {
        "status": "success",
        "plugin_id": resolved_id,
        "dependencies": deps,
        "target": str(target),
    }


def ensure_deps_on_path(capabilities_dir: Path, plugin_id: str) -> Path | None:
    """Insert plugin sandbox site-packages on sys.path if present."""
    site = plugin_site_packages(capabilities_dir, plugin_id)
    if not site.is_dir():
        return None
    site_str = str(site)
    if site_str not in sys.path:
        sys.path.insert(0, site_str)
    return site


def remove_deps_from_path(site: Path | None) -> None:
    if site is None:
        return
    site_str = str(site)
    while site_str in sys.path:
        sys.path.remove(site_str)
