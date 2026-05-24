"""Device Connect plugin host — dynamic capability loading under one credential."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from device_connect_edge.drivers import DeviceDriver, emit, rpc
from device_connect_edge.drivers.capability_loader import CapabilityDriverMixin, LoadedCapability
from device_connect_edge.types import DeviceIdentity, DeviceStatus

from device_connect_plugin_driver.authoring import build_authoring_guide, build_plugin_template, list_plugin_examples
from device_connect_plugin_driver.concentrator import SidecarConcentrator, SidecarSpec
from device_connect_plugin_driver.plugin_delivery import (
    DeliveryConfig,
    decode_bundle,
    extract_plugin_archive,
    fetch_url,
    parse_docker_manifest,
    verify_digest,
)
from device_connect_plugin_driver.sidecar_proxy import SidecarProxyRegistry

logger = logging.getLogger(__name__)


class PluginHostDriver(CapabilityDriverMixin, DeviceDriver):
    """Device Connect driver that loads Python capability plugins at runtime.

  All loaded capability RPCs are exposed on **this** device identity — agents
  and portal callers use the same credential whether the host has zero or
  twenty plugins loaded.
    """

    device_type = "plugin_host"

    labels = {
        "category": "hub",
        "plugin_driver:role": "plugin_host",
        "plugin_driver:authoring_rpc": "get_plugin_authoring_guide",
        "plugin_driver:template_rpc": "get_plugin_template",
        "plugin_driver:examples_rpc": "list_plugin_examples",
    }

    def __init__(
        self,
        *,
        capabilities_dir: Path | str,
        auto_load: bool = True,
        enable_sidecars: bool = False,
        sidecar_network: str = "dc-plugin-network",
        host_label: str | None = None,
    ) -> None:
        super().__init__()
        self._capabilities_dir = Path(capabilities_dir).expanduser().resolve()
        self._auto_load = auto_load
        self._enable_sidecars = enable_sidecars
        self._host_label = host_label
        self._connected = False
        self._sidecar_proxy = SidecarProxyRegistry()
        self._concentrator: SidecarConcentrator | None = None
        self._delivery_config = DeliveryConfig.from_env()
        if enable_sidecars:
            self._concentrator = SidecarConcentrator(network=sidecar_network)
        self.init_capabilities(self._capabilities_dir)

    @property
    def identity(self) -> DeviceIdentity:
        model = "Plugin Host"
        if self._host_label:
            model = f"{model} ({self._host_label})"
        return DeviceIdentity(
            device_type=self.device_type,
            manufacturer="Device Connect",
            model=model,
            description=(
                "Dynamic plugin host — load Python capabilities in-process or via sidecar containers"
            ),
        )

    @property
    def status(self) -> DeviceStatus:
        availability = "idle" if self._connected else "offline"
        return DeviceStatus(ts=datetime.now(UTC), availability=availability)

    async def connect(self) -> None:
        self._capabilities_dir.mkdir(parents=True, exist_ok=True)
        if self._auto_load:
            count = await self.load_capabilities()
            logger.info("Auto-loaded %d capabilities from %s", count, self._capabilities_dir)
        if self._concentrator is not None:
            await self._concentrator.ensure_network()
        self._connected = True
        logger.info(
            "Plugin host connected (capabilities_dir=%s sidecars=%s)",
            self._capabilities_dir,
            self._enable_sidecars,
        )

    async def disconnect(self) -> None:
        if self._concentrator is not None:
            await self._concentrator.stop_all()
        await self._sidecar_proxy.clear()
        await self.unload_capabilities()
        self._connected = False
        logger.info("Plugin host disconnected")

    async def _refresh_mesh_advertisement(self) -> None:
        """Push updated capability lists to registry (portal) or D2D presence."""
        runtime = getattr(self, "_device", None)
        if runtime is None:
            logger.debug("No DeviceRuntime bound; skipping mesh refresh")
            return

        if getattr(runtime, "_d2d_mode", False):
            announcer = getattr(runtime, "_d2d_announcer", None)
            if announcer is not None:
                announcer._capabilities = self.capabilities.model_dump()
                announcer.trigger_burst()
                logger.info("Refreshed D2D presence advertisement")
            return

        await runtime._register(force=True)
        logger.info("Re-registered device with updated capabilities")

    def _capability_summary(self, loaded: LoadedCapability) -> dict[str, Any]:
        manifest = loaded.manifest
        return {
            "id": loaded.id,
            "functions": list(loaded.functions),
            "routines": list(loaded.routines),
            "manifest": {
                "id": manifest.get("id", loaded.id),
                "description": manifest.get("description"),
                "version": manifest.get("version"),
                "entry_point": manifest.get("entry_point", "capability.py"),
                "class_name": manifest.get("class_name"),
            },
        }

    @rpc()
    async def get_status(self) -> dict[str, Any]:
        """Return plugin host connectivity and configuration."""
        loaded = self.get_loaded_capabilities()
        sidecars = await self._sidecar_proxy.list_sidecars() if self._sidecar_proxy else {}
        return {
            "status": "success",
            "connected": self._connected,
            "device_type": self.device_type,
            "capabilities_dir": str(self._capabilities_dir),
            "auto_load": self._auto_load,
            "enable_sidecars": self._enable_sidecars,
            "loaded_count": len(loaded),
            "sidecar_count": len(sidecars),
            "loaded_plugins": list(loaded.keys()),
            "authoring": {
                "guide_rpc": "get_plugin_authoring_guide",
                "template_rpc": "get_plugin_template",
                "examples_rpc": "list_plugin_examples",
                "agents_doc": "AGENTS.md",
            },
        }

    @rpc()
    async def get_plugin_authoring_guide(self) -> dict[str, Any]:
        """Return structured plugin authoring instructions and doc pointers for agents.

        Call this first when building a new capability. Includes manifest schema,
        install methods, workflow steps, and URLs to AGENTS.md / templates / examples.
        """
        guide = build_authoring_guide()
        guide["status"] = "success"
        return guide

    @rpc()
    async def get_plugin_template(
        self,
        plugin_id: str,
        class_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Render manifest.json and capability.py scaffold for a new plugin.

        Args:
            plugin_id: Plugin slug (e.g. garage-door, tempest-weather).
            class_name: Optional Python class name (default: derived from plugin_id).
            description: Optional human-readable description for manifest and docstrings.
        """
        try:
            template = build_plugin_template(
                plugin_id=plugin_id,
                class_name=class_name,
                description=description,
            )
            return {"status": "success", **template}
        except Exception as exc:
            logger.exception("get_plugin_template failed")
            return {"status": "error", "message": str(exc), "plugin_id": plugin_id}

    @rpc()
    async def list_plugin_examples(self) -> dict[str, Any]:
        """List bundled plugin examples and template locations for agents."""
        return list_plugin_examples()

    @rpc()
    async def list_plugins(self) -> dict[str, Any]:
        """List loaded plugins and available capability directories on disk."""
        loaded = {
            cap_id: self._capability_summary(info)
            for cap_id, info in self.get_loaded_capabilities().items()
        }
        available: list[dict[str, Any]] = []
        if self._capabilities_dir.is_dir():
            for path in sorted(self._capabilities_dir.iterdir()):
                if not path.is_dir():
                    continue
                manifest_path = path / "manifest.json"
                entry: dict[str, Any] = {"id": path.name, "path": str(path), "loaded": path.name in loaded}
                if manifest_path.is_file():
                    try:
                        entry["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError as exc:
                        entry["manifest_error"] = str(exc)
                else:
                    entry["manifest_error"] = "missing manifest.json"
                available.append(entry)
        sidecars = await self._sidecar_proxy.list_sidecars()
        return {
            "status": "success",
            "loaded": loaded,
            "available": available,
            "sidecars": sidecars,
            "capabilities_dir": str(self._capabilities_dir),
        }

    @rpc()
    async def load_plugin(self, plugin_id: str) -> dict[str, Any]:
        """Load a capability plugin by directory name under capabilities_dir.

        Args:
            plugin_id: Capability folder name (must contain manifest.json).
        """
        ok = await self.load_capability(plugin_id)
        if not ok:
            return {
                "status": "error",
                "plugin_id": plugin_id,
                "message": f"Failed to load plugin '{plugin_id}'",
            }
        await self._refresh_mesh_advertisement()
        loaded = self.get_loaded_capabilities().get(plugin_id)
        summary = self._capability_summary(loaded) if loaded else {"id": plugin_id}
        return {"status": "success", "plugin": summary}

    @rpc()
    async def unload_plugin(self, plugin_id: str) -> dict[str, Any]:
        """Unload a previously loaded capability plugin.

        Args:
            plugin_id: Capability identifier to unload.
        """
        ok = await self.unload_capability(plugin_id)
        if not ok:
            return {
                "status": "error",
                "plugin_id": plugin_id,
                "message": f"Plugin '{plugin_id}' is not loaded",
            }
        await self._refresh_mesh_advertisement()
        return {"status": "success", "plugin_id": plugin_id}

    @rpc()
    async def reload_plugin(self, plugin_id: str) -> dict[str, Any]:
        """Unload and reload a capability plugin (picks up code changes on disk).

        Args:
            plugin_id: Capability identifier to reload.
        """
        await self.unload_capability(plugin_id)
        ok = await self.load_capability(plugin_id)
        if not ok:
            return {
                "status": "error",
                "plugin_id": plugin_id,
                "message": f"Failed to reload plugin '{plugin_id}'",
            }
        await self._refresh_mesh_advertisement()
        loaded = self.get_loaded_capabilities().get(plugin_id)
        summary = self._capability_summary(loaded) if loaded else {"id": plugin_id}
        return {"status": "success", "plugin": summary}

    @rpc()
    async def install_plugin(self, source_path: str, plugin_id: str | None = None) -> dict[str, Any]:
        """Copy a capability directory into capabilities_dir and optionally load it.

        Args:
            source_path: Path to a folder containing manifest.json + entry_point.
            plugin_id: Target folder name (defaults to manifest id or source folder name).
        """
        src = Path(source_path).expanduser().resolve()
        if not src.is_dir():
            return {"status": "error", "message": f"Source path is not a directory: {src}"}
        manifest_path = src / "manifest.json"
        if not manifest_path.is_file():
            return {"status": "error", "message": f"Missing manifest.json in {src}"}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        target_id = plugin_id or manifest.get("id") or src.name
        dest = self._capabilities_dir / target_id
        if dest.exists():
            return {
                "status": "error",
                "message": f"Plugin '{target_id}' already exists at {dest}",
            }
        shutil.copytree(src, dest)
        load_result = await self.load_plugin(target_id)
        return {
            "status": "success" if load_result.get("status") == "success" else "partial",
            "plugin_id": target_id,
            "installed_to": str(dest),
            "load_result": load_result,
        }

    async def _install_extracted_plugin(
        self,
        plugin_id: str,
        *,
        load: bool = True,
    ) -> dict[str, Any]:
        dest = self._capabilities_dir / plugin_id
        if not (dest / "manifest.json").is_file():
            return {
                "status": "error",
                "plugin_id": plugin_id,
                "message": f"Installed plugin missing manifest.json at {dest}",
            }
        if not load:
            return {
                "status": "success",
                "plugin_id": plugin_id,
                "installed_to": str(dest),
                "loaded": False,
            }
        load_result = await self.load_plugin(plugin_id)
        return {
            "status": "success" if load_result.get("status") == "success" else "partial",
            "plugin_id": plugin_id,
            "installed_to": str(dest),
            "load_result": load_result,
        }

    @rpc()
    async def install_plugin_from_url(
        self,
        url: str,
        plugin_id: str | None = None,
        digest: str | None = None,
        format: str = "auto",
        load: bool = True,
    ) -> dict[str, Any]:
        """Download a plugin archive from HTTPS and install it on this host.

        Args:
            url: HTTPS URL to a .tar.gz, .tgz, or .zip capability archive.
            plugin_id: Optional target folder name (defaults to manifest id).
            digest: Optional sha256 digest (hex or sha256:hex) for verification.
            format: Archive format — auto, tar.gz, tgz, or zip.
            load: Load the plugin into the running host after extract (default true).
        """
        try:
            data = await fetch_url(url, config=self._delivery_config)
            verify_digest(
                data,
                digest,
                require=self._delivery_config.require_digest,
            )
            fmt = format if format in {"auto", "tar.gz", "tgz", "zip"} else "auto"
            resolved_id, _dest = extract_plugin_archive(
                data,
                dest_parent=self._capabilities_dir,
                plugin_id=plugin_id,
                archive_format=fmt,  # type: ignore[arg-type]
                filename=url,
            )
            return await self._install_extracted_plugin(resolved_id, load=load)
        except Exception as exc:
            logger.exception("install_plugin_from_url failed")
            return {"status": "error", "message": str(exc), "url": url}

    @rpc()
    async def install_plugin_from_bundle(
        self,
        bundle_b64: str,
        plugin_id: str | None = None,
        digest: str | None = None,
        format: str = "auto",
        load: bool = True,
    ) -> dict[str, Any]:
        """Install a plugin from a base64-encoded archive (.tar.gz or .zip).

        Args:
            bundle_b64: Base64-encoded plugin archive bytes.
            plugin_id: Optional target folder name (defaults to manifest id).
            digest: Optional sha256 digest (hex or sha256:hex) for verification.
            format: Archive format — auto, tar.gz, tgz, or zip.
            load: Load the plugin after extract (default true).
        """
        try:
            data = decode_bundle(bundle_b64, max_bytes=self._delivery_config.max_bytes)
            verify_digest(
                data,
                digest,
                require=self._delivery_config.require_digest,
            )
            fmt = format if format in {"auto", "tar.gz", "tgz", "zip"} else "auto"
            resolved_id, _dest = extract_plugin_archive(
                data,
                dest_parent=self._capabilities_dir,
                plugin_id=plugin_id,
                archive_format=fmt,  # type: ignore[arg-type]
            )
            return await self._install_extracted_plugin(resolved_id, load=load)
        except Exception as exc:
            logger.exception("install_plugin_from_bundle failed")
            return {"status": "error", "message": str(exc)}

    @rpc()
    async def install_plugin_from_docker(
        self,
        manifest: dict[str, Any],
        *,
        load: bool = True,
    ) -> dict[str, Any]:
        """Deploy a container plugin from a docker manifest (sidecar proxied on this host).

        Requires --enable-sidecars. The container image must expose the dc-plugin sidecar
        HTTP API (/health, /invoke/{function}) unless you mount a local capability.

        Args:
            manifest: DockerPluginManifest fields — id, image, port, env, pull, digest.
            load: Register proxied RPCs after deploy (default true).
        """
        if self._concentrator is None:
            return {
                "status": "error",
                "message": "Sidecars disabled. Restart with --enable-sidecars or DC_PLUGIN_ENABLE_SIDECARS=1",
            }
        try:
            parsed = parse_docker_manifest(manifest)
            cap_path = self._capabilities_dir / parsed.id
            spec = SidecarSpec(
                plugin_id=parsed.id,
                image=parsed.image,
                port=parsed.port,
                capability_path=cap_path if cap_path.is_dir() else None,
                env=parsed.env,
                pull=parsed.pull,
                digest=parsed.digest,
            )
            deployment = await self._concentrator.deploy(spec)
            if load:
                await self._sidecar_proxy.register_sidecar(
                    plugin_id=parsed.id,
                    base_url=deployment.base_url,
                    driver=self,
                )
                await self._refresh_mesh_advertisement()
            return {
                "status": "success",
                "plugin_id": parsed.id,
                "mode": "docker_sidecar",
                "deployment": deployment.model_dump(),
            }
        except Exception as exc:
            logger.exception("install_plugin_from_docker failed")
            return {"status": "error", "message": str(exc)}

    @rpc()
    async def install_plugin_from_manifest(
        self,
        manifest: dict[str, Any],
        *,
        load: bool = True,
    ) -> dict[str, Any]:
        """Install a plugin from a typed manifest (python bundle metadata or docker).

        Args:
            manifest: Unified manifest. type=docker delegates to install_plugin_from_docker.
                type=python requires bundle_b64 or url plus optional digest/format.
            load: Load or register after install (default true).
        """
        manifest_type = manifest.get("type", "python")
        if manifest_type == "docker":
            return await self.install_plugin_from_docker(manifest, load=load)

        if manifest_type != "python":
            return {"status": "error", "message": f"unsupported manifest type: {manifest_type}"}

        if "bundle_b64" in manifest:
            return await self.install_plugin_from_bundle(
                bundle_b64=manifest["bundle_b64"],
                plugin_id=manifest.get("id"),
                digest=manifest.get("digest"),
                format=manifest.get("format", "auto"),
                load=load,
            )
        if "url" in manifest:
            return await self.install_plugin_from_url(
                url=manifest["url"],
                plugin_id=manifest.get("id"),
                digest=manifest.get("digest"),
                format=manifest.get("format", "auto"),
                load=load,
            )
        return {
            "status": "error",
            "message": "python manifest requires bundle_b64 or url",
        }

    @rpc()
    async def deploy_sidecar(
        self,
        plugin_id: str,
        *,
        image: str | None = None,
        port: int = 8787,
    ) -> dict[str, Any]:
        """Deploy a capability as an isolated container sidecar (requires docker extra).

        The sidecar loads one capability and exposes HTTP invoke locally. RPCs are
        proxied through this host so agents still use the host credential.

        Args:
            plugin_id: Capability directory name under capabilities_dir.
            image: Optional pre-built sidecar image (default: dc-plugin-sidecar:local).
            port: Sidecar HTTP port inside the container network.
        """
        if self._concentrator is None:
            return {
                "status": "error",
                "message": "Sidecars disabled. Restart with --enable-sidecars or DC_PLUGIN_ENABLE_SIDECARS=1",
            }
        cap_path = self._capabilities_dir / plugin_id
        if not cap_path.is_dir():
            return {"status": "error", "message": f"Capability not found: {cap_path}"}

        spec = SidecarSpec(
            plugin_id=plugin_id,
            capability_path=cap_path,
            image=image or "dc-plugin-sidecar:local",
            port=port,
        )
        deployment = await self._concentrator.deploy(spec)
        await self._sidecar_proxy.register_sidecar(
            plugin_id=plugin_id,
            base_url=deployment.base_url,
            driver=self,
        )
        await self._refresh_mesh_advertisement()
        return {"status": "success", "deployment": deployment.model_dump()}

    @rpc()
    async def undeploy_sidecar(self, plugin_id: str) -> dict[str, Any]:
        """Stop a sidecar container and remove proxied RPCs.

        Args:
            plugin_id: Sidecar / capability identifier.
        """
        if self._concentrator is None:
            return {"status": "error", "message": "Sidecars are not enabled on this host"}
        await self._sidecar_proxy.unregister_sidecar(plugin_id)
        stopped = await self._concentrator.stop(plugin_id)
        await self._refresh_mesh_advertisement()
        return {"status": "success", "plugin_id": plugin_id, "stopped": stopped}

    @emit()
    async def plugin_loaded(self, plugin_id: str, functions: list[str]) -> None:
        """Emitted when a plugin is loaded onto the host."""
        pass

    @emit()
    async def plugin_unloaded(self, plugin_id: str) -> None:
        """Emitted when a plugin is unloaded from the host."""
        pass

    async def invoke(self, function_name: str, **params) -> Any:
        if function_name in self._sidecar_proxy.get_functions():
            return await self._sidecar_proxy.invoke(function_name, **params)
        return await super().invoke(function_name, **params)

    def _get_functions(self) -> dict[str, Any]:
        funcs = super()._get_functions()
        funcs.update(self._sidecar_proxy.get_functions())
        return funcs
