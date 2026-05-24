"""HTTP sidecar that runs a single capability outside the plugin host process."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from aiohttp import web

from device_connect_edge.drivers.capability_loader import CapabilityLoader
logger = logging.getLogger(__name__)


async def _emit_noop(_event_name: str, _payload: dict) -> None:
    return None


def _build_app(loader: CapabilityLoader, plugin_id: str) -> web.Application:
    app = web.Application()

    async def health(_request: web.Request) -> web.Response:
        caps = loader.get_capabilities()
        return web.json_response(
            {
                "status": "ok",
                "plugin_id": plugin_id,
                "loaded": plugin_id in caps,
                "functions": list(loader.get_functions().keys()),
            }
        )

    async def list_functions(_request: web.Request) -> web.Response:
        funcs = loader.get_functions()
        schemas = {}
        for cap_id, loaded in loader.get_capabilities().items():
            for name, schema in loaded.function_schemas.items():
                schemas[name] = schema
                schemas[f"{cap_id}.{name}"] = schema
        return web.json_response({"functions": list(funcs.keys()), "schemas": schemas})

    async def invoke(request: web.Request) -> web.Response:
        function_name = request.match_info["function_name"]
        try:
            body = await request.json() if request.can_read_body else {}
        except json.JSONDecodeError:
            return web.json_response({"status": "error", "message": "invalid JSON body"}, status=400)
        if not isinstance(body, dict):
            body = {}
        try:
            result = await loader.invoke(function_name, **body)
            return web.json_response({"status": "success", "result": result})
        except KeyError:
            return web.json_response(
                {"status": "error", "message": f"unknown function: {function_name}"},
                status=404,
            )
        except Exception as exc:
            logger.exception("Sidecar invoke failed for %s", function_name)
            return web.json_response({"status": "error", "message": str(exc)}, status=500)

    async def schema(request: web.Request) -> web.Response:
        function_name = request.match_info["function_name"]
        for loaded in loader.get_capabilities().values():
            if function_name in loaded.function_schemas:
                schema = loaded.function_schemas[function_name]
                return web.json_response({"function": function_name, **schema})
            prefixed = f"{loaded.id}.{function_name}"
            if prefixed in loader.get_functions() and function_name in loaded.function_schemas:
                schema = loaded.function_schemas[function_name]
                return web.json_response({"function": function_name, **schema})
        return web.json_response({"status": "error", "message": "not found"}, status=404)

    app.router.add_get("/health", health)
    app.router.add_get("/functions", list_functions)
    app.router.add_post("/invoke/{function_name}", invoke)
    app.router.add_get("/schema/{function_name}", schema)
    return app


async def run_sidecar(
    *,
    capability_dir: Path,
    plugin_id: str | None,
    host: str,
    port: int,
) -> None:
    capability_dir = capability_dir.expanduser().resolve()
    manifest_path = capability_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Sidecar requires manifest.json in {capability_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    resolved_id = plugin_id or manifest.get("id") or capability_dir.name

    loader = CapabilityLoader(
        event_emitter=_emit_noop,
        capabilities_dir=capability_dir.parent,
        tenant=os.getenv("TENANT", "default"),
    )
    ok = await loader.load_one(resolved_id)
    if not ok:
        raise SystemExit(f"Failed to load capability '{resolved_id}' from {capability_dir}")

    await loader.start_all_routines()
    app = _build_app(loader, resolved_id)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("DC plugin sidecar listening on %s:%d (plugin=%s)", host, port, resolved_id)

    stop = asyncio.Event()
    try:
        await stop.wait()
    finally:
        await loader.unload_all()
        await runner.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Device Connect capability as an HTTP sidecar.")
    parser.add_argument(
        "--capability-dir",
        default=os.getenv("DC_PLUGIN_CAPABILITY_DIR", "."),
        help="Directory containing manifest.json (default: DC_PLUGIN_CAPABILITY_DIR or cwd)",
    )
    parser.add_argument("--plugin-id", default=os.getenv("DC_PLUGIN_PLUGIN_ID"))
    parser.add_argument("--host", default=os.getenv("DC_PLUGIN_SIDECAR_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DC_PLUGIN_SIDECAR_PORT", "8787")))
    return parser


def main() -> None:
    logging.basicConfig(level=os.getenv("DC_PLUGIN_LOG_LEVEL", "INFO"))
    args = build_parser().parse_args()
    asyncio.run(
        run_sidecar(
            capability_dir=Path(args.capability_dir),
            plugin_id=args.plugin_id,
            host=args.host,
            port=args.port,
        )
    )


if __name__ == "__main__":
    main()
