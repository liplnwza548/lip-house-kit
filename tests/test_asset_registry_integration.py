"""Integration: real 13 files under ASSET_ROOT. Skips (with reason) when unset.

Run: ASSET_ROOT=/home/box/subtitle-work/assets pytest tests/test_asset_registry_integration.py -q
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import validate_registry as vr

pytestmark = pytest.mark.skipif(
    not os.environ.get("ASSET_ROOT"),
    reason="ASSET_ROOT not set — integration needs the real 13 media files")


def test_real_registry_ok():
    root = Path(os.environ["ASSET_ROOT"])
    reg = json.loads((ROOT / "assets" / "registry.json").read_text())
    assert len(reg["assets"]) == 13
    assert vr.validate(reg, root) == []
