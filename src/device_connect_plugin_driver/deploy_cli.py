"""Deploy plugins to a remote plugin_host over Device Connect (agent-friendly CLI)."""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

from device_connect_plugin_driver.plugin_delivery import sha256_hex
from device_connect_plugin_driver.plugin_validation import validate_plugin
from device_connect_plugin_driver.remote_client import (
    PluginHostClient,
    RemoteConnectConfig,
    RemoteInvokeError,
    connect_plugin_host,
    parse_params_json,
)


def pack_plugin_directory(plugin_dir: Path) -> bytes:
    plugin_dir = plugin_dir.resolve()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        archive.add(plugin_dir, arcname=plugin_dir.name)
    return buf.getvalue()


def _emit(result: Any, *, as_json: bool, ok: bool = True) -> None:
    if as_json:
        payload = {"status": "success" if ok else "error", "result": result}
        if not ok and isinstance(result, str):
            payload = {"status": "error", "message": result}
        print(json.dumps(payload, indent=2, default=str))
    elif isinstance(result, dict):
        status = result.get("status", "ok")
        print(f"status: {status}")
        for key, value in result.items():
            if key != "status":
                print(f"  {key}: {value}")
    else:
        print(result)


def _emit_error(message: str, *, as_json: bool, code: int = 1) -> None:
    if as_json:
        print(json.dumps({"status": "error", "message": message}, indent=2))
    else:
        print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--host",
        required=True,
        help="Target plugin_host device id (e.g. plugin-host-1)",
    )
    parser.add_argument("--tenant", default=None, help="Device Connect tenant (default: env or 'default')")
    parser.add_argument(
        "--credentials",
        "--portal-credentials",
        dest="credentials",
        default=None,
        help="Invoker NATS credentials file (.creds.json) with permission to call the host",
    )
    parser.add_argument(
        "--nats-url",
        action="append",
        default=None,
        help="NATS server URL (repeatable; default: NATS_URL / portal URL)",
    )
    parser.add_argument(
        "--messaging-backend",
        default=None,
        help="Messaging backend (default: nats)",
    )
    parser.add_argument("--timeout", type=float, default=None, help="RPC timeout seconds (default: 60)")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON on stdout")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and show planned action without invoking the host",
    )


def _connect_config(args: argparse.Namespace) -> RemoteConnectConfig:
    urls: tuple[str, ...] = tuple(args.nats_url) if args.nats_url else ()
    return RemoteConnectConfig.from_env(
        host_id=args.host,
        tenant=args.tenant,
        credentials_file=args.credentials,
        messaging_backend=args.messaging_backend,
        messaging_urls=urls or None,
        timeout=args.timeout,
    )


async def _with_client(args: argparse.Namespace, fn) -> Any:
    config = _connect_config(args)
    if args.dry_run:
        return await fn(None, config)
    client = await connect_plugin_host(config)
    try:
        return await fn(client, config)
    finally:
        await client.close()


async def _cmd_install(args: argparse.Namespace) -> None:
    async def run(client: PluginHostClient | None, config: RemoteConnectConfig) -> Any:
        if args.url:
            params: dict[str, Any] = {
                "url": args.url,
                "load": not args.no_load,
            }
            if args.digest:
                params["digest"] = args.digest
            if args.plugin_id:
                params["plugin_id"] = args.plugin_id
            if args.install_dependencies:
                params["install_dependencies"] = True
            if args.dry_run:
                return {"action": "install_plugin_from_url", "host": config.host_id, **params}
            return await client.invoke("install_plugin_from_url", params)

        if not args.plugin_path:
            _emit_error("plugin path or --url required", as_json=args.json)

        plugin_dir = Path(args.plugin_path).expanduser().resolve()
        validation = None
        if not args.skip_validate:
            validation = validate_plugin(plugin_dir)
            if not validation.ok:
                _emit_error(
                    "; ".join(validation.errors) or "validation failed",
                    as_json=args.json,
                )

        archive = pack_plugin_directory(plugin_dir)
        digest = args.digest or f"sha256:{sha256_hex(archive)}"
        bundle_b64 = base64.b64encode(archive).decode("ascii")
        plugin_id = args.plugin_id
        if not plugin_id:
            if validation is not None:
                plugin_id = validation.plugin_id
            else:
                manifest = json.loads((plugin_dir / "manifest.json").read_text(encoding="utf-8"))
                plugin_id = manifest.get("id", plugin_dir.name)

        params = {
            "bundle_b64": bundle_b64,
            "digest": digest,
            "load": not args.no_load,
        }
        if plugin_id:
            params["plugin_id"] = plugin_id
        if args.install_dependencies:
            params["install_dependencies"] = True

        if args.dry_run:
            return {
                "action": "install_plugin_from_bundle",
                "host": config.host_id,
                "plugin_id": plugin_id,
                "digest": digest,
                "archive_bytes": len(archive),
                "load": not args.no_load,
            }

        return await client.invoke("install_plugin_from_bundle", params)

    try:
        result = await _with_client(args, run)
        _emit(result, as_json=args.json)
    except RemoteInvokeError as exc:
        _emit_error(str(exc), as_json=args.json)


async def _cmd_load(args: argparse.Namespace) -> None:
    async def run(client: PluginHostClient | None, config: RemoteConnectConfig) -> Any:
        params: dict[str, Any] = {"plugin_id": args.plugin_id}
        if args.install_dependencies:
            params["install_dependencies"] = True
        if args.dry_run:
            return {"action": "load_plugin", "host": config.host_id, **params}
        return await client.invoke("load_plugin", params)

    try:
        result = await _with_client(args, run)
        _emit(result, as_json=args.json)
    except RemoteInvokeError as exc:
        _emit_error(str(exc), as_json=args.json)


async def _cmd_unload(args: argparse.Namespace) -> None:
    async def run(client: PluginHostClient | None, config: RemoteConnectConfig) -> Any:
        if args.dry_run:
            return {"action": "unload_plugin", "host": config.host_id, "plugin_id": args.plugin_id}
        return await client.invoke("unload_plugin", {"plugin_id": args.plugin_id})

    try:
        result = await _with_client(args, run)
        _emit(result, as_json=args.json)
    except RemoteInvokeError as exc:
        _emit_error(str(exc), as_json=args.json)


async def _cmd_reload(args: argparse.Namespace) -> None:
    async def run(client: PluginHostClient | None, config: RemoteConnectConfig) -> Any:
        if args.dry_run:
            return {"action": "reload_plugin", "host": config.host_id, "plugin_id": args.plugin_id}
        return await client.invoke("reload_plugin", {"plugin_id": args.plugin_id})

    try:
        result = await _with_client(args, run)
        _emit(result, as_json=args.json)
    except RemoteInvokeError as exc:
        _emit_error(str(exc), as_json=args.json)


async def _cmd_list(args: argparse.Namespace) -> None:
    async def run(client: PluginHostClient | None, config: RemoteConnectConfig) -> Any:
        if args.dry_run:
            return {"action": "list_plugins", "host": config.host_id}
        return await client.invoke("list_plugins", {})

    try:
        result = await _with_client(args, run)
        _emit(result, as_json=args.json)
    except RemoteInvokeError as exc:
        _emit_error(str(exc), as_json=args.json)


async def _cmd_status(args: argparse.Namespace) -> None:
    async def run(client: PluginHostClient | None, config: RemoteConnectConfig) -> Any:
        if args.dry_run:
            return {"action": "get_status", "host": config.host_id}
        return await client.invoke("get_status", {})

    try:
        result = await _with_client(args, run)
        _emit(result, as_json=args.json)
    except RemoteInvokeError as exc:
        _emit_error(str(exc), as_json=args.json)


async def _cmd_invoke(args: argparse.Namespace) -> None:
    async def run(client: PluginHostClient | None, config: RemoteConnectConfig) -> Any:
        params = parse_params_json(args.params)
        if args.dry_run:
            return {"action": args.function, "host": config.host_id, "params": params}
        return await client.invoke(args.function, params)

    try:
        result = await _with_client(args, run)
        if args.json:
            print(json.dumps({"status": "success", "result": result}, indent=2, default=str))
        else:
            print(json.dumps(result, indent=2, default=str))
    except (RemoteInvokeError, ValueError) as exc:
        _emit_error(str(exc), as_json=args.json)


def deploy_main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    parent = argparse.ArgumentParser(add_help=False)
    _add_connection_args(parent)

    parser = argparse.ArgumentParser(
        description="Deploy and manage plugins on a remote Device Connect plugin_host.",
        parents=[parent],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    install_p = sub.add_parser(
        "install",
        help="Pack a local plugin folder and install on the host (install_plugin_from_bundle)",
        parents=[parent],
        conflict_handler="resolve",
    )
    install_p.add_argument("plugin_path", nargs="?", help="Local plugin directory")
    install_p.add_argument("--url", help="HTTPS artifact URL (install_plugin_from_url instead of bundle)")
    install_p.add_argument("--digest", help="sha256 digest (computed automatically for local bundles)")
    install_p.add_argument("--plugin-id", help="Target folder name on host (default: manifest id)")
    install_p.add_argument("--no-load", action="store_true", help="Install files only; do not load into runtime")
    install_p.add_argument("--skip-validate", action="store_true", help="Skip local manifest validation")
    install_p.add_argument(
        "--install-dependencies",
        action="store_true",
        help="Request opt-in pip install from manifest on the host",
    )

    load_p = sub.add_parser("load", help="Load an installed plugin by id", parents=[parent], conflict_handler="resolve")
    load_p.add_argument("plugin_id")
    load_p.add_argument("--install-dependencies", action="store_true")

    unload_p = sub.add_parser("unload", help="Unload a plugin", parents=[parent], conflict_handler="resolve")
    unload_p.add_argument("plugin_id")

    reload_p = sub.add_parser("reload", help="Reload a plugin", parents=[parent], conflict_handler="resolve")
    reload_p.add_argument("plugin_id")

    sub.add_parser("list", help="List plugins on the host", parents=[parent], conflict_handler="resolve")
    sub.add_parser("status", help="Host status", parents=[parent], conflict_handler="resolve")

    invoke_p = sub.add_parser("invoke", help="Invoke any host RPC", parents=[parent], conflict_handler="resolve")
    invoke_p.add_argument("function", help="RPC name (e.g. hello_world, get_plugin_template)")
    invoke_p.add_argument("--params", default="{}", help="JSON object of RPC parameters")

    args = parser.parse_args(argv)

    handlers = {
        "install": _cmd_install,
        "load": _cmd_load,
        "unload": _cmd_unload,
        "reload": _cmd_reload,
        "list": _cmd_list,
        "status": _cmd_status,
        "invoke": _cmd_invoke,
    }
    try:
        asyncio.run(handlers[args.command](args))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
