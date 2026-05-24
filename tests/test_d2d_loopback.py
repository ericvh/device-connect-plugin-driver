"""Loopback D2D simulation: load_plugin then hello_world (single process, no NATS)."""

from __future__ import annotations

import asyncio
import os

import pytest

from device_connect_edge import DeviceRuntime
from device_connect_edge.device import _RemoteInvoker
from device_connect_edge.messaging import create_client

from device_connect_plugin_driver.plugin_host import PluginHostDriver
from tests.integration.conftest import HOST_DEVICE_ID, TENANT
from tests.integration.loopback_messaging import install_loopback_backend


@pytest.mark.asyncio
async def test_loopback_load_plugin_and_hello_world(capabilities_dir) -> None:
    install_loopback_backend()
    os.environ["DEVICE_CONNECT_DISCOVERY_MODE"] = "d2d"

    host = PluginHostDriver(
        capabilities_dir=capabilities_dir,
        auto_load=False,
        enable_sidecars=False,
    )
    host_rt = DeviceRuntime(
        driver=host,
        device_id=HOST_DEVICE_ID,
        tenant=TENANT,
        messaging_backend="loopback",
        messaging_urls=["loopback://local"],
        allow_insecure=True,
    )

    host_task = asyncio.create_task(host_rt.run())
    await asyncio.sleep(0.5)

    client = create_client("loopback")
    await client.connect(servers=["loopback://local"])
    remote = _RemoteInvoker(client, tenant=TENANT, timeout=10.0)

    try:
        load_resp = await remote.invoke(HOST_DEVICE_ID, "load_plugin", params={"plugin_id": "hello-world"})
        assert "error" not in load_resp, load_resp
        assert load_resp["result"]["status"] == "success"

        hello_resp = await remote.invoke(
            HOST_DEVICE_ID,
            "hello_world",
            params={"name": "loopback"},
        )
        assert "error" not in hello_resp, hello_resp
        assert hello_resp["result"] == {"message": "Hello, loopback!"}
    finally:
        await client.close()
        await host_rt.stop()
        try:
            await asyncio.wait_for(host_task, timeout=10)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
