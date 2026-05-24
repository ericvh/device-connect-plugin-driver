"""Integration test fixtures."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_DEVICE_ID = "plugin-host-itest"
TENANT = "itest"


def nats_available() -> bool:
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    if not url.startswith("nats://"):
        return False
    host_port = url.removeprefix("nats://")
    host, _, port = host_port.partition(":")
    port = int(port or 4222)
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture
def plugin_host_env(capabilities_dir: Path) -> dict[str, str]:
    nats_url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    return {
        "DEVICE_CONNECT_ALLOW_INSECURE": "true",
        "DEVICE_CONNECT_DISCOVERY_MODE": "d2d",
        "MESSAGING_BACKEND": "nats",
        "NATS_URL": nats_url,
        "MESSAGING_URLS": nats_url,
        "PYTHONUNBUFFERED": "1",
        "DC_PLUGIN_CAPABILITIES_DIR": str(capabilities_dir),
    }


@pytest.fixture
def plugin_host_process(plugin_host_env: dict[str, str]):
    """Spawn plugin host in a separate process (requires NATS)."""
    if not nats_available():
        pytest.skip("NATS not reachable — start nats or set NATS_URL")

    cmd = [
        sys.executable,
        "-m",
        "tests.integration.plugin_host_runner",
        "--device-id",
        HOST_DEVICE_ID,
        "--tenant",
        TENANT,
        "--capabilities-dir",
        plugin_host_env["DC_PLUGIN_CAPABILITIES_DIR"],
        "--no-auto-load",
    ]
    proc = subprocess.Popen(
        cmd,
        env={**os.environ, **plugin_host_env},
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(2.0)
    if proc.poll() is not None:
        output = proc.stdout.read() if proc.stdout else ""
        pytest.fail(f"plugin host exited early:\n{output}")

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
