"""Example capability plugin — replace with your service description."""

from __future__ import annotations

from device_connect_edge.drivers.decorators import emit, periodic, rpc


class MyServiceCapability:
    """Device Connect capability plugin for my-service.

    Copy this folder or call get_plugin_template on a plugin_host to scaffold
    a plugin for a different id/class name.
    """

    def __init__(self, device=None) -> None:
        self.device = device

    async def start(self) -> None:
        """Called when the plugin is loaded onto the host."""
        pass

    async def stop(self) -> None:
        """Called when the plugin is unloaded."""
        pass

    @rpc()
    async def get_service_status(self) -> dict:
        """Return health/status for this service."""
        return {"status": "ok", "plugin_id": "my-service"}

    @rpc()
    async def run_action(self, action: str = "default", **params) -> dict:
        """Primary service action — implement your integration here.

        Args:
            action: Short action name your service understands.
            **params: Action-specific parameters.
        """
        return {"status": "success", "action": action, "params": params}
