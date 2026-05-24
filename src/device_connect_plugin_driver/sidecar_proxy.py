"""Proxy sidecar RPCs through the plugin host DeviceDriver."""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable

import aiohttp

from device_connect_edge.drivers.decorators import rpc

logger = logging.getLogger(__name__)


class SidecarProxyRegistry:
    """Register dynamic RPC handlers that forward to HTTP sidecars."""

    def __init__(self) -> None:
        self._sidecars: dict[str, str] = {}
        self._functions: dict[str, str] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def list_sidecars(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        session = await self._get_session()
        for plugin_id, base_url in self._sidecars.items():
            entry: dict[str, Any] = {"base_url": base_url, "functions": []}
            try:
                async with session.get(f"{base_url}/health", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    entry["health"] = await resp.json()
            except Exception as exc:
                entry["health_error"] = str(exc)
            entry["functions"] = [
                name for name, origin in self._functions.items() if origin == plugin_id
            ]
            out[plugin_id] = entry
        return out

    async def register_sidecar(self, *, plugin_id: str, base_url: str, driver: Any) -> None:
        session = await self._get_session()
        async with session.get(f"{base_url}/functions", timeout=aiohttp.ClientTimeout(total=5)) as resp:
            payload = await resp.json()
        function_names = payload.get("functions", [])

        self._sidecars[plugin_id] = base_url.rstrip("/")
        for name in function_names:
            if name.startswith(f"{plugin_id}."):
                short = name.split(".", 1)[1]
                self._bind_function(plugin_id, short, base_url)
            elif "." not in name:
                self._bind_function(plugin_id, name, base_url)

        driver._invalidate_caches()
        logger.info("Registered sidecar %s with %d functions", plugin_id, len(function_names))

    def _bind_function(self, plugin_id: str, name: str, base_url: str) -> None:
        if name in self._handlers:
            return

        async def handler(**params: Any) -> Any:
            session = await self._get_session()
            async with session.post(
                f"{base_url.rstrip('/')}/invoke/{name}",
                json=params,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                body = await resp.json()
                if body.get("status") != "success":
                    raise RuntimeError(body.get("message", f"sidecar invoke failed ({resp.status})"))
                return body.get("result")

        handler.__name__ = f"sidecar_{plugin_id}_{name}"
        decorated = rpc(name=name)(handler)
        self._handlers[name] = decorated
        self._functions[name] = plugin_id

    async def unregister_sidecar(self, plugin_id: str) -> None:
        self._sidecars.pop(plugin_id, None)
        to_remove = [name for name, origin in self._functions.items() if origin == plugin_id]
        for name in to_remove:
            self._functions.pop(name, None)
            self._handlers.pop(name, None)

    def get_functions(self) -> dict[str, Callable[..., Any]]:
        return dict(self._handlers)

    async def invoke(self, function_name: str, **params: Any) -> Any:
        handler = self._handlers[function_name]
        if inspect.iscoroutinefunction(handler):
            return await handler(**params)
        return handler(**params)

    async def clear(self) -> None:
        self._sidecars.clear()
        self._functions.clear()
        self._handlers.clear()
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None
