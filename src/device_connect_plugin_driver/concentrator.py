"""Docker concentrator for isolated capability sidecars."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SidecarSpec(BaseModel):
    plugin_id: str
    image: str = "dc-plugin-sidecar:local"
    port: int = 8787
    capability_path: Path | None = None
    env: dict[str, str] = Field(default_factory=dict)
    pull: bool = True
    digest: str | None = None


class SidecarDeployment(BaseModel):
    plugin_id: str
    container_id: str
    container_name: str
    base_url: str
    image: str
    port: int
    mode: str = "sidecar"


class SidecarConcentrator:
    """Manage Docker sidecars that run dc-plugin-sidecar or custom sidecar images."""

    def __init__(self, *, network: str = "dc-plugin-network") -> None:
        self._network = network
        self._deployments: dict[str, SidecarDeployment] = {}

    def _docker(self):
        try:
            import docker
        except ImportError as exc:
            raise RuntimeError(
                "Docker support requires the concentrator extra: pip install device-connect-plugin-driver[concentrator]"
            ) from exc
        return docker.from_env()

    async def ensure_network(self) -> None:
        client = self._docker()
        try:
            client.networks.get(self._network)
        except Exception:
            client.networks.create(self._network, driver="bridge")
            logger.info("Created Docker network %s", self._network)

    async def deploy(self, spec: SidecarSpec) -> SidecarDeployment:
        if spec.plugin_id in self._deployments:
            return self._deployments[spec.plugin_id]

        client = self._docker()
        container_name = f"dc-plugin-sidecar-{spec.plugin_id}"
        for existing in client.containers.list(all=True, filters={"name": container_name}):
            existing.remove(force=True)

        if spec.pull:
            client.images.pull(spec.image)

        run_kwargs: dict[str, Any] = {
            "name": container_name,
            "detach": True,
            "network": self._network,
            "ports": {f"{spec.port}/tcp": None},
            "restart_policy": {"Name": "unless-stopped"},
        }

        environment = dict(spec.env)
        environment.setdefault("DC_PLUGIN_PLUGIN_ID", spec.plugin_id)
        environment.setdefault("DC_PLUGIN_SIDECAR_PORT", str(spec.port))
        run_kwargs["environment"] = environment

        if spec.capability_path is not None:
            parent_mount = str(spec.capability_path.resolve().parent)
            run_kwargs["volumes"] = {parent_mount: {"bind": "/capabilities", "mode": "ro"}}
            environment.setdefault(
                "DC_PLUGIN_CAPABILITY_DIR",
                f"/capabilities/{spec.capability_path.name}",
            )

        container = client.containers.run(spec.image, **run_kwargs)
        container.reload()
        host_port = int(container.attrs["NetworkSettings"]["Ports"][f"{spec.port}/tcp"][0]["HostPort"])
        base_url = f"http://127.0.0.1:{host_port}"

        deployment = SidecarDeployment(
            plugin_id=spec.plugin_id,
            container_id=container.id,
            container_name=container_name,
            base_url=base_url,
            image=spec.image,
            port=spec.port,
        )
        self._deployments[spec.plugin_id] = deployment
        logger.info(
            "Deployed sidecar %s -> %s (container=%s image=%s)",
            spec.plugin_id,
            base_url,
            container_name,
            spec.image,
        )
        return deployment

    async def stop(self, plugin_id: str) -> bool:
        deployment = self._deployments.pop(plugin_id, None)
        client = self._docker()
        if deployment is not None:
            try:
                container = client.containers.get(deployment.container_id)
                container.remove(force=True)
                return True
            except Exception as exc:
                logger.warning("Failed to remove sidecar container for %s: %s", plugin_id, exc)
        container_name = f"dc-plugin-sidecar-{plugin_id}"
        for existing in client.containers.list(all=True, filters={"name": container_name}):
            existing.remove(force=True)
            return True
        return False

    async def stop_all(self) -> None:
        plugin_ids = list(self._deployments.keys())
        for plugin_id in plugin_ids:
            await self.stop(plugin_id)
