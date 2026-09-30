"""Unit tests: dummy media in tmp_path, NO real assets, NO ASSET_ROOT needed.

Covers: valid registry passes; missing file; SHA mismatch; duplicate ID;
license gap; path escape; non-object entry; bad kind/mood; bad SHA format;
negative duration; unapproved asset.
"""
import copy
import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import validate_registry as vr


def tiny_wav(p: Path, seconds=0.1):
    n = int(44100 * seconds)
    p.write_bytes(b"RIFF" + struct.pack("<I", 36 + n * 2) + b"WAVEfmt " +
                  struct.pack("<IHHIIHH", 16, 1, 1, 44100, 88200, 2, 16) +
                  b"data" + struct.pack("<I", n * 2) + b"\x00" * (n * 2))


def good_bgm(logical="bgm/x.mp3", **kw):
    d = {"asset_id": "t-bgm", "kind": "bgm", "logical_path": logical,
         "sha256": "0" * 64, "source_url": "https://example.com/x",
         "license_name": "X", "license_evidence": "https://example.com/lic",
         "commercial_use": True, "attribution_required": False,
         "duration_s": 1.0, "mood": "general_sales", "energy": "medium",
         "approved": True, "approved_by": "T", "approved_at": "2026-09-30",
         "bpm": None, "instrumental": True, "vocal_presence": "none",
         "loop_safe": True}
    d.update(kw)
    return d


@pytest.fixture()
def stage(tmp_path):
    root = tmp_path / "assets"
    (root / "bgm").mkdir(parents=True)
    (root / "sfx").mkdir(parents=True)
    tiny_wav(root / "bgm" / "x.mp3")
    tiny_wav(root / "sfx" / "y.wav")
    import hashlib
    reg = {"registry_version": 1, "assets": [
        good_bgm(),
        dict(good_bgm(), asset_id="t-sfx", kind="sfx", logical_path="sfx/y.wav",
             mood="neutral",
             event_types=["ui_tick"], min_gap_s=3.0, avoid_during=["price"]),
    ]}
    for a in reg["assets"]:
        a["sha256"] = hashlib.sha256((root / a["logical_path"]).read_bytes()).hexdigest()
    return root, reg


def test_valid_passes(stage):
    root, reg = stage
    assert vr.validate(reg, root) == []


def test_missing_file(stage):
    root, reg = stage
    (root / "bgm" / "x.mp3").unlink()
    errs = vr.validate(reg, root)
    assert any("FILE MISSING" in e for e in errs)


def test_sha_mismatch(stage):
    root, reg = stage
    reg["assets"][0]["sha256"] = "f" * 64
    assert any("SHA MISMATCH" in e for e in vr.validate(reg, root))


def test_duplicate_id(stage):
    root, reg = stage
    reg["assets"].append(copy.deepcopy(reg["assets"][0]))
    assert any("DUPLICATE" in e for e in vr.validate(reg, root))


def test_license_gap(stage):
    root, reg = stage
    reg["assets"][0]["license_evidence"] = ""
    assert any("license" in e.lower() for e in vr.validate(reg, root))


def test_path_escape(stage):
    root, reg = stage
    reg["assets"][0]["logical_path"] = "../evil.mp3"
    assert any("escapes" in e or "relative" in e for e in vr.validate(reg, root))


def test_non_object_entry(stage):
    root, reg = stage
    reg["assets"].append("not-an-object")
    assert any("not an object" in e for e in vr.validate(reg, root))


def test_bad_kind_mood(stage):
    root, reg = stage
    reg["assets"][0]["kind"] = "video"
    reg["assets"][1]["mood"] = "hyper"
    errs = vr.validate(reg, root)
    assert sum(1 for e in errs if e.startswith("schema")) >= 2


def test_bad_sha_format_and_negative_duration(stage):
    root, reg = stage
    reg["assets"][0]["sha256"] = "xyz"
    reg["assets"][0]["duration_s"] = -1.0
    errs = vr.validate(reg, root)
    assert sum(1 for e in errs if e.startswith("schema")) >= 2


def test_unapproved(stage):
    root, reg = stage
    reg["assets"][0]["approved"] = False
    assert any("NOT APPROVED" in e for e in vr.validate(reg, root))


def test_errors_fresh_each_run(stage):
    import hashlib
    root, reg = stage
    real_sha = hashlib.sha256((root / "bgm" / "x.mp3").read_bytes()).hexdigest()
    reg["assets"][0]["sha256"] = "f" * 64
    assert len(vr.validate(reg, root)) >= 1
    reg["assets"][0]["sha256"] = real_sha
    assert vr.validate(reg, root) == []
