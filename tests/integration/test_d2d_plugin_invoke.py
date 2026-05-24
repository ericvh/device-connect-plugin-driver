"""Two-process D2D integration: load_plugin then hello_world over NATS."""

from __future__ import annotations

import os

import pytest

from device_connect_edge.device import _RemoteInvoker
from device_connect_edge.messaging import create_client

from tests.integration.conftest import HOST_DEVICE_ID, TENANT


async def _invoke(remote: _RemoteInvoker, function: str, params: dict | None = None) -> dict:
    response = await remote.invoke(HOST_DEVICE_ID, function, params=params or {})
    assert "error" not in response, response
    return response.get("result", response)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_two_process_load_plugin_and_hello_world(plugin_host_process) -> None:
    nats_url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    client = create_client("nats")
    await client.connect(servers=[nats_url])
    remote = _RemoteInvoker(client, tenant=TENANT, timeout=15.0)

    try:
        load_result = await _invoke(remote, "load_plugin", {"plugin_id": "hello-world"})
        assert load_result["status"] == "success"

        greeting = await _invoke(remote, "hello_world", {"name": "integration"})
        assert greeting == {"message": "Hello, integration!"}
    finally:
        await client.close()
