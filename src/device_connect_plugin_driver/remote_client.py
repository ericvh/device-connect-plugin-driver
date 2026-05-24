"""Connect to a remote plugin_host and invoke RPCs (for deploy CLI and agents)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from device_connect_edge.device import _RemoteInvoker
from device_connect_edge.messaging import create_client
from device_connect_edge.messaging.config import MessagingConfig

from device_connect_plugin_driver.config import (
    PORTAL_NATS_URL,
    load_portal_credentials,
    resolve_portal_credentials_file,
)


class RemoteInvokeError(RuntimeError):
    """RPC returned an error or invalid response."""

    def __init__(self, message: str, *, response: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.response = response


@dataclass(frozen=True)
class RemoteConnectConfig:
    host_id: str
    tenant: str = "default"
    messaging_backend: str = "nats"
    messaging_urls: tuple[str, ...] = ()
    credentials_file: str | None = None
    timeout: float = 60.0

    @classmethod
    def from_env(
        cls,
        *,
        host_id: str,
        tenant: str | None = None,
        credentials_file: str | None = None,
        messaging_backend: str | None = None,
        messaging_urls: tuple[str, ...] | None = None,
        timeout: float | None = None,
    ) -> RemoteConnectConfig:
        urls: tuple[str, ...] = messaging_urls or ()
        if not urls:
            raw = os.environ.get("MESSAGING_URLS") or os.environ.get("NATS_URL", "")
            urls = tuple(part.strip() for part in raw.split(",") if part.strip())
        if not urls:
            urls = (PORTAL_NATS_URL,)

        creds = credentials_file or resolve_portal_credentials_file(
            explicit_path=os.environ.get("NATS_CREDENTIALS_FILE")
            or os.environ.get("PORTAL_CREDENTIALS_FILE"),
            portal=True,
            pattern="*.creds.json",
            search_dir=os.environ.get(
                "PORTAL_CREDENTIALS_DIR",
                str(os.path.expanduser("~/.config/device-connect")),
            ),
        )

        resolved_tenant = tenant or os.environ.get("TENANT", "default")
        if creds:
            try:
                portal = load_portal_credentials(creds)
                if portal.messaging_urls and not urls:
                    urls = portal.messaging_urls
                if portal.tenant and tenant is None:
                    resolved_tenant = portal.tenant
            except (OSError, ValueError):
                pass

        return cls(
            host_id=host_id,
            tenant=resolved_tenant,
            messaging_backend=messaging_backend or os.environ.get("MESSAGING_BACKEND", "nats"),
            messaging_urls=urls,
            credentials_file=creds,
            timeout=timeout if timeout is not None else float(os.environ.get("DC_PLUGIN_DEPLOY_TIMEOUT", "60")),
        )


def _load_nats_credentials(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return MessagingConfig._load_credentials_file(path)


class PluginHostClient:
    """Async client for plugin_host management and delivery RPCs."""

    def __init__(self, remote: _RemoteInvoker, *, host_id: str) -> None:
        self._remote = remote
        self.host_id = host_id

    async def invoke(self, function: str, params: dict[str, Any] | None = None) -> Any:
        response = await self._remote.invoke(
            self.host_id,
            function,
            params=params or {},
        )
        if "error" in response:
            err = response["error"]
            message = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RemoteInvokeError(message, response=response)
        if "result" in response:
            return response["result"]
        return response

    async def close(self) -> None:
        messaging = self._remote._messaging
        if hasattr(messaging, "close"):
            await messaging.close()
        elif hasattr(messaging, "disconnect"):
            await messaging.disconnect()


async def connect_plugin_host(config: RemoteConnectConfig) -> PluginHostClient:
    """Open messaging connection and return a client for the target plugin_host."""
    credentials = _load_nats_credentials(config.credentials_file)
    msg_config = MessagingConfig(
        backend=config.messaging_backend,
        servers=list(config.messaging_urls),
        credentials=credentials,
    )
    client = create_client(msg_config.backend)
    await client.connect(servers=msg_config.servers, credentials=msg_config.credentials)
    remote = _RemoteInvoker(client, tenant=config.tenant, timeout=config.timeout)
    return PluginHostClient(remote, host_id=config.host_id)


def parse_params_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("params must be a JSON object")
    return data
