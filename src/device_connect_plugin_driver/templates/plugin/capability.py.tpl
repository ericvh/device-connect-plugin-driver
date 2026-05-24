"""{{DESCRIPTION}}"""

from __future__ import annotations

from device_connect_edge.drivers.decorators import emit, periodic, rpc


class {{CLASS_NAME}}:
    """Device Connect capability plugin for {{PLUGIN_ID}}.

    Replace RPC bodies with logic for your service. The host loads this module
    from manifest.json and exposes @rpc methods on the plugin_host device.
    """

    def __init__(self, device=None) -> None:
        self.device = device

    async def start(self) -> None:
        """Optional lifecycle hook — called when the plugin is loaded."""
        pass

    async def stop(self) -> None:
        """Optional lifecycle hook — called when the plugin is unloaded."""
        pass

    @rpc()
    async def get_service_status(self) -> dict:
        """Return health/status for this service."""
        return {"status": "ok", "plugin_id": "{{PLUGIN_ID}}"}

    @rpc()
    async def run_action(self, action: str = "default", **params) -> dict:
        """Primary service action — rename and implement for your integration.

        Args:
            action: Short action name your service understands.
            **params: Action-specific parameters.
        """
        # TODO: implement {{PLUGIN_ID}} service logic here
        return {"status": "success", "action": action, "params": params}

    # Optional: emit events back to the mesh
    # @emit()
    # async def service_event(self, detail: str) -> None:
    #     """Emitted when something interesting happens."""
    #     pass

    # Optional: background polling (started after host registration)
    # @periodic(interval=30.0)
    # async def poll_service(self) -> None:
    #     """Poll hardware or upstream API periodically."""
    #     pass
