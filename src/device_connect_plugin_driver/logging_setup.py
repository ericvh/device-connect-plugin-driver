"""Logging configuration for the Device Connect plugin host."""

from __future__ import annotations

import logging
import os


def configure_driver_logging() -> None:
    level_name = os.environ.get("DC_PLUGIN_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("device_connect_edge").setLevel(level)
