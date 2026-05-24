"""Hello-world capability — smallest useful plugin for smoke tests."""

from __future__ import annotations

from device_connect_edge.drivers.decorators import rpc


class HelloWorldCapability:
    """Single-RPC plugin used to verify plugin load and mesh invoke."""

    def __init__(self, device=None) -> None:
        self.device = device

    @rpc()
    async def hello_world(self, name: str = "world") -> dict:
        """Return a greeting — use this to confirm the plugin is loaded and reachable.

        Args:
            name: Name to greet (default: world).
        """
        return {"message": f"Hello, {name}!"}
