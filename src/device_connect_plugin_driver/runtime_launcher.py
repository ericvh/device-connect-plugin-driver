"""Shared async startup for the Device Connect plugin host CLI."""

from __future__ import annotations

import logging
import os
import sys
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

from device_connect_edge import DeviceRuntime

from device_connect_plugin_driver.config import (
    DriverConfig,
    PortalCredentials,
    apply_portal_config,
    load_portal_credentials,
    resolve_portal_credentials_file,
)
from device_connect_plugin_driver.logging_setup import configure_driver_logging
from device_connect_plugin_driver.plugin_host import PluginHostDriver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceConnectRunParams:
    driver_config: DriverConfig
    portal_credentials: PortalCredentials | None


def log_run_config(params: DeviceConnectRunParams) -> None:
    cfg = params.driver_config
    creds = cfg.nats_credentials_file or "(none)"
    urls = ", ".join(cfg.messaging_urls) if cfg.messaging_urls else "(default / D2D)"
    logger.info("=== Device Connect plugin host (device-connect) ===")
    logger.info(
        "device_id=%s tenant=%s portal=%s capabilities_dir=%s auto_load=%s sidecars=%s",
        cfg.device_id,
        cfg.tenant,
        cfg.portal,
        cfg.capabilities_dir,
        cfg.auto_load,
        cfg.enable_sidecars,
    )
    logger.info(
        "messaging backend=%s urls=%s credentials=%s allow_insecure=%s discovery=%s",
        cfg.messaging_backend or "(default)",
        urls,
        creds,
        cfg.allow_insecure,
        cfg.discovery_mode or "(default)",
    )


def gather_cli_run_params(args: Namespace) -> DeviceConnectRunParams:
    env = DriverConfig.from_env()
    portal = args.portal or env.portal
    messaging_urls = tuple(args.messaging_url) if args.messaging_url else env.messaging_urls
    allow_insecure = args.allow_insecure or env.allow_insecure
    credentials_file = resolve_portal_credentials_file(
        explicit_path=args.portal_credentials or args.nats_credentials_file or env.nats_credentials_file,
        portal=portal,
        pattern=args.portal_credentials_glob or env.portal_credentials_glob,
        search_dir=args.portal_credentials_dir or env.portal_credentials_dir,
    )
    if portal and not credentials_file:
        print(
            "Portal mode requires credentials. Provide --portal-credentials, "
            "--nats-credentials-file, NATS_CREDENTIALS_FILE, or place a matching "
            f"file under {args.portal_credentials_dir or env.portal_credentials_dir}.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    portal_credentials = None
    if credentials_file:
        portal_credentials = load_portal_credentials(credentials_file)

    config = DriverConfig(
        device_id=args.device_id or env.device_id,
        tenant=args.tenant or env.tenant,
        capabilities_dir=args.capabilities_dir or env.capabilities_dir,
        auto_load=not args.no_auto_load and env.auto_load,
        enable_sidecars=args.enable_sidecars or env.enable_sidecars,
        sidecar_network=args.sidecar_network or env.sidecar_network,
        messaging_backend=args.messaging_backend or env.messaging_backend,
        messaging_urls=messaging_urls,
        nats_credentials_file=credentials_file,
        allow_insecure=allow_insecure,
        portal=portal,
        portal_credentials_glob=args.portal_credentials_glob or env.portal_credentials_glob,
        portal_credentials_dir=args.portal_credentials_dir or env.portal_credentials_dir,
        discovery_mode=args.discovery_mode or env.discovery_mode,
        local_zenoh_routes=env.local_zenoh_routes,
    )
    config = apply_portal_config(
        config,
        portal_credentials=portal_credentials,
        explicit_device_id=args.device_id,
        explicit_tenant=args.tenant,
    )
    return DeviceConnectRunParams(driver_config=config, portal_credentials=portal_credentials)


async def run_device_connect(params: DeviceConnectRunParams) -> None:
    configure_driver_logging()
    cfg = params.driver_config
    log_run_config(params)

    if cfg.discovery_mode:
        os.environ.setdefault("DEVICE_CONNECT_DISCOVERY_MODE", cfg.discovery_mode)
    if cfg.local_zenoh_routes:
        os.environ.setdefault(
            "DEVICE_CONNECT_LOCAL_ZENOH_ROUTES",
            ",".join(cfg.local_zenoh_routes),
        )

    driver = PluginHostDriver(
        capabilities_dir=Path(cfg.capabilities_dir),
        auto_load=cfg.auto_load,
        enable_sidecars=cfg.enable_sidecars,
        sidecar_network=cfg.sidecar_network,
        host_label=cfg.device_id,
    )
    runtime = DeviceRuntime(
        driver=driver,
        device_id=cfg.device_id,
        tenant=cfg.tenant,
        messaging_backend=cfg.messaging_backend,
        messaging_urls=list(cfg.messaging_urls) or None,
        nats_credentials_file=cfg.nats_credentials_file,
        allow_insecure=cfg.allow_insecure,
    )

    logger.info("Starting DeviceRuntime (Device Connect plugin host)")
    try:
        await runtime.run()
    except Exception:
        logger.exception("Device Connect runtime failed")
        raise
