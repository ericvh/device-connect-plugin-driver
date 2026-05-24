"""Tests for plugin driver configuration helpers."""

from __future__ import annotations

import json
from pathlib import Path

from device_connect_plugin_driver.config import apply_portal_config, DriverConfig, load_portal_credentials


def test_apply_portal_config_sets_infra_discovery(tmp_path: Path) -> None:
    creds_path = tmp_path / "device.creds.json"
    creds_path.write_text(
        json.dumps(
            {
                "device_id": "from-creds",
                "tenant": "lab",
                "nats": {"urls": ["nats://example:4222"]},
            }
        )
    )
    creds = load_portal_credentials(creds_path)
    config = apply_portal_config(
        DriverConfig(portal=True),
        portal_credentials=creds,
        explicit_device_id=None,
        explicit_tenant=None,
    )
    assert config.device_id == "from-creds"
    assert config.tenant == "lab"
    assert config.discovery_mode == "infra"
    assert config.messaging_urls == ("nats://example:4222",)
