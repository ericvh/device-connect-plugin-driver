"""CLI runner for the Device Connect plugin host."""

from __future__ import annotations

import argparse
import asyncio

from device_connect_plugin_driver.logging_setup import configure_driver_logging
from device_connect_plugin_driver.runtime_launcher import gather_cli_run_params, run_device_connect

configure_driver_logging()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Device Connect Plugin Driver — Device Connect plugin host (load capabilities under one credential).",
    )
    parser.add_argument("--device-id", default=None, help="Device Connect device id")
    parser.add_argument("--tenant", default=None, help="Device Connect tenant")
    parser.add_argument(
        "--capabilities-dir",
        default=None,
        help="Directory of capability plugin folders (default: ./capabilities or DC_PLUGIN_CAPABILITIES_DIR)",
    )
    parser.add_argument(
        "--no-auto-load",
        action="store_true",
        help="Do not load all capabilities from capabilities-dir on startup.",
    )
    parser.add_argument(
        "--enable-sidecars",
        action="store_true",
        help="Enable Docker sidecar deployment RPCs (requires device-connect-plugin-driver[concentrator]).",
    )
    parser.add_argument(
        "--sidecar-network",
        default=None,
        help="Docker network for plugin sidecars (default: dc-plugin-network).",
    )
    parser.add_argument("--messaging-backend", default=None)
    parser.add_argument("--messaging-url", action="append", default=None)
    parser.add_argument("--nats-credentials-file", default=None)
    parser.add_argument(
        "--portal",
        action="store_true",
        help="Connect via Device Connect Portal (NATS + registry).",
    )
    parser.add_argument("--portal-credentials", default=None)
    parser.add_argument("--portal-credentials-glob", default=None)
    parser.add_argument("--portal-credentials-dir", default=None)
    parser.add_argument(
        "--allow-insecure",
        action="store_true",
        help="Allow insecure Device Connect (D2D dev only).",
    )
    parser.add_argument(
        "--discovery-mode",
        default=None,
        choices=["d2d", "p2p", "infra"],
        help="Override DEVICE_CONNECT_DISCOVERY_MODE.",
    )
    return parser


async def _run_cli(args: argparse.Namespace) -> None:
    params = gather_cli_run_params(args)
    await run_device_connect(params)


def main() -> None:
    asyncio.run(_run_cli(build_parser().parse_args()))


if __name__ == "__main__":
    main()
