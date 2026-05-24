"""CLI runner for the Device Connect plugin host."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from device_connect_plugin_driver.artifact_store import ArtifactServer, ArtifactStore, ArtifactStoreConfig
from device_connect_plugin_driver.logging_setup import configure_driver_logging
from device_connect_plugin_driver.plugin_validation import validate_plugin
from device_connect_plugin_driver.runtime_launcher import gather_cli_run_params, run_device_connect

configure_driver_logging()


def build_run_parser() -> argparse.ArgumentParser:
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
    parser.add_argument(
        "--artifact-serve",
        action="store_true",
        help="Serve local plugin artifact store over HTTP (also DC_PLUGIN_ARTIFACT_SERVE=1).",
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
    if args.artifact_serve:
        import os

        os.environ["DC_PLUGIN_ARTIFACT_SERVE"] = "1"
    params = gather_cli_run_params(args)
    await run_device_connect(params)


def _validate_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Validate a plugin directory layout.")
    parser.add_argument("plugin_path", help="Path to plugin folder containing manifest.json")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)
    result = validate_plugin(args.plugin_path)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Plugin: {result.plugin_id or '(unknown)'}")
        print(f"Path:   {result.path}")
        print(f"Status: {'OK' if result.ok else 'FAILED'}")
        if result.rpc_methods:
            print(f"RPCs:   {', '.join(result.rpc_methods)}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        for error in result.errors:
            print(f"error: {error}")
    raise SystemExit(0 if result.ok else 1)


async def _artifact_serve_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Serve the local plugin artifact store.")
    parser.add_argument("--capabilities-dir", default="./capabilities")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    from pathlib import Path

    config = ArtifactStoreConfig.from_env(capabilities_dir=Path(args.capabilities_dir))
    host = args.host or config.serve_host
    port = args.port or config.serve_port
    store = ArtifactStore(config)
    server = ArtifactServer(store, host=host, port=port)
    await server.start()
    print(f"Artifact server listening on {server.base_url}/artifacts")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await server.stop()


def _artifact_publish_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Publish a plugin to the local artifact store.")
    parser.add_argument("plugin_path", help="Path to plugin folder")
    parser.add_argument("--capabilities-dir", default="./capabilities")
    parser.add_argument("--plugin-id", default=None)
    parser.add_argument("--version", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    from pathlib import Path

    plugin_path = Path(args.plugin_path).expanduser().resolve()
    config = ArtifactStoreConfig.from_env(capabilities_dir=Path(args.capabilities_dir))
    store = ArtifactStore(config)
    record = store.publish_plugin_dir(
        plugin_path,
        plugin_id=args.plugin_id,
        version=args.version,
    )
    artifact = record.to_dict()
    artifact["url"] = store.get_artifact(record.plugin_id)["url"]
    if args.json:
        print(json.dumps(artifact, indent=2))
    else:
        print(f"Published {record.plugin_id} -> {artifact['url']}")
        print(f"Digest: sha256:{record.digest}")
    raise SystemExit(0)


def _artifact_list_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="List published plugin artifacts.")
    parser.add_argument("--capabilities-dir", default="./capabilities")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    from pathlib import Path

    config = ArtifactStoreConfig.from_env(capabilities_dir=Path(args.capabilities_dir))
    store = ArtifactStore(config)
    artifacts = store.list_artifacts()
    if args.json:
        print(json.dumps({"artifacts": artifacts}, indent=2))
    else:
        if not artifacts:
            print("No artifacts published.")
        for item in artifacts:
            print(f"{item['plugin_id']}\t{item.get('digest', '')}\t{item.get('url', '')}")
    raise SystemExit(0)


def _artifact_main(argv: list[str]) -> None:
    if not argv or argv[0] in {"-h", "--help"}:
        parser = argparse.ArgumentParser(description="Manage the local plugin artifact store.")
        parser.add_argument("command", choices=["publish", "list", "serve"], nargs="?")
        parser.print_help()
        raise SystemExit(0 if not argv else 2)
    command, rest = argv[0], argv[1:]
    if command == "publish":
        _artifact_publish_main(rest)
    if command == "list":
        _artifact_list_main(rest)
    if command == "serve":
        asyncio.run(_artifact_serve_main(rest))
    print(f"Unknown artifact command: {command}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        _validate_main(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "artifact":
        _artifact_main(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        from device_connect_plugin_driver.deploy_cli import deploy_main

        deploy_main(sys.argv[2:])
        return
    asyncio.run(_run_cli(build_run_parser().parse_args()))


if __name__ == "__main__":
    main()
