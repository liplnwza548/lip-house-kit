#!/usr/bin/env python3
"""Validate assets/registry.json against real files under ASSET_ROOT.

Fails LOUD (non-zero exit + reason) when: file missing, SHA mismatch,
license evidence incomplete, asset unapproved, duplicate ID, path escapes
ASSET_ROOT, or schema shape invalid.

Usage: ASSET_ROOT=/home/box/subtitle-work/assets python3 tools/validate_registry.py
"""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "assets" / "registry.json"
ASSET_ROOT = Path(os.environ.get("ASSET_ROOT", "/home/box/subtitle-work/assets")).resolve()

ERRORS: list = []


def fail(msg):
    ERRORS.append(msg)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    try:
        reg = json.loads(REG.read_text())
    except Exception as e:
        print(f"REGISTRY_UNREADABLE: {e}")
        return 2
    assets = reg.get("assets")
    if not isinstance(assets, list) or not assets:
        print("REGISTRY_EMPTY: 'assets' must be a non-empty list")
        return 2

    seen = set()
    base = {"asset_id", "kind", "logical_path", "sha256", "source_url",
            "license_name", "license_evidence", "commercial_use",
            "attribution_required", "duration_s", "mood", "energy",
            "approved", "approved_by", "approved_at"}
    for i, a in enumerate(assets):
        tag = a.get("asset_id", f"index#{i}")
        if not isinstance(a, dict):
            fail(f"{tag}: entry is not an object")
            continue
        missing = base - set(a.keys())
        if missing:
            fail(f"{tag}: missing fields {sorted(missing)}")
        if a.get("kind") == "bgm":
            for k in ("bpm", "instrumental", "vocal_presence", "loop_safe"):
                if k not in a:
                    fail(f"{tag}: bgm missing '{k}'")
        if a.get("kind") == "sfx":
            for k in ("event_types", "min_gap_s", "avoid_during"):
                if k not in a:
                    fail(f"{tag}: sfx missing '{k}'")
        if tag in seen:
            fail(f"{tag}: DUPLICATE asset_id")
        seen.add(tag)
        if not a.get("approved"):
            fail(f"{tag}: NOT APPROVED (approved=false)")
        for k in ("license_name", "license_evidence", "source_url"):
            if not a.get(k):
                fail(f"{tag}: incomplete license evidence ('{k}' empty)")
        if a.get("kind") == "bgm" and not a.get("commercial_use"):
            fail(f"{tag}: bgm not cleared for commercial use")
        lp = a.get("logical_path", "")
        if not lp or lp.startswith("/") or ".." in Path(lp).parts:
            fail(f"{tag}: logical_path '{lp}' must be relative inside ASSET_ROOT")
            continue
        real = (ASSET_ROOT / lp).resolve()
        try:
            real.relative_to(ASSET_ROOT)
        except ValueError:
            fail(f"{tag}: path escapes ASSET_ROOT: {lp}")
            continue
        if not real.is_file():
            fail(f"{tag}: FILE MISSING: {lp} (ASSET_ROOT={ASSET_ROOT})")
            continue
        if real.suffix.lower() in (".mp3", ".wav", ".ogg", ".flac", ".m4a"):
            actual = sha256(real)
            if actual != a.get("sha256"):
                fail(f"{tag}: SHA MISMATCH for {lp}\n  registry: {a.get('sha256')}\n  actual:   {actual}")

    if ERRORS:
        print(f"REGISTRY_INVALID: {len(ERRORS)} problem(s) (ASSET_ROOT={ASSET_ROOT})")
        for e in ERRORS:
            print(" -", e)
        return 1
    print(f"REGISTRY_OK: {len(assets)} assets approved+verified (ASSET_ROOT={ASSET_ROOT})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
