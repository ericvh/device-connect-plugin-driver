"""Test package root — ensures repo root is importable."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HELLO_WORLD = ROOT / "examples" / "hello-world"


@pytest.fixture
def capabilities_dir(tmp_path: Path) -> Path:
    dest = tmp_path / "capabilities"
    shutil.copytree(HELLO_WORLD, dest / "hello-world")
    return dest
