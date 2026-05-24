"""Subprocess entrypoint: run plugin host until SIGTERM."""

from __future__ import annotations

import argparse
import asyncio
import signal

from device_connect_plugin_driver.plugin_host import PluginHostDriver
from device_connect_edge import DeviceRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Integration test plugin host runner")
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--tenant", default="itest")
    parser.add_argument("--capabilities-dir", required=True)
    parser.add_argument("--no-auto-load", action="store_true")
    return parser


async def run_host(args: argparse.Namespace) -> None:
    stop = asyncio.Event()

    def _stop(*_sig: int) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    driver = PluginHostDriver(
        capabilities_dir=args.capabilities_dir,
        auto_load=not args.no_auto_load,
        enable_sidecars=False,
    )
    runtime = DeviceRuntime(
        driver=driver,
        device_id=args.device_id,
        tenant=args.tenant,
        allow_insecure=True,
    )

    task = asyncio.create_task(runtime.run())
    await stop.wait()
    await runtime.stop()
    await task


def main() -> None:
    asyncio.run(run_host(build_parser().parse_args()))


if __name__ == "__main__":
    main()
