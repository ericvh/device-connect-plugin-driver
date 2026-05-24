"""Demo capability for the Device Connect plugin host."""

from __future__ import annotations

from device_connect_edge.drivers.decorators import emit, rpc


class DemoCapability:
    """Minimal capability illustrating the manifest + @rpc pattern."""

    def __init__(self, device=None) -> None:
        self.device = device
        self._tick = 0

    @rpc()
    async def ping(self) -> dict:
        """Health check for the demo plugin."""
        return {"pong": True, "plugin": "demo"}

    @rpc()
    async def echo(self, message: str = "hello") -> dict:
        """Echo a message back to the caller.

        Args:
            message: Text to echo.
        """
        self._tick += 1
        return {"message": message, "tick": self._tick}

    @emit()
    async def demo_ready(self, plugin: str = "demo") -> None:
        """Emitted when the demo capability is ready."""
        pass
