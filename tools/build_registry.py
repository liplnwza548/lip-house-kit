#!/usr/bin/env python3
"""Refresh measured fields (sha256, duration_s) in assets/registry.json.

Single-source rule: metadata (license, mood, approval) lives ONLY in
registry.json — this tool never writes metadata, only re-measures files.
Edit the JSON directly for metadata changes, then run this to refresh.

Usage: ASSET_ROOT=/home/box/subtitle-work/assets python3 tools/build_registry.py
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def resolve_root(explicit=None) -> Path:
    raw = explicit or os.environ.get("ASSET_ROOT")
    if not raw:
        raise SystemExit("ASSET_ROOT is not set (refusing VM-default guess). "
                         "Example: ASSET_ROOT=/home/box/subtitle-work/assets")
    return Path(raw)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True, check=True)
    return round(float(r.stdout.strip()), 2)


def main(asset_root=None) -> int:
    root = resolve_root(asset_root)
    reg_path = ROOT / "assets" / "registry.json"
    reg = json.loads(reg_path.read_text())
    n = 0
    for a in reg["assets"]:
        lp = a["logical_path"]
        if lp.startswith("/") or ".." in Path(lp).parts:
            raise SystemExit(f"REFUSED: logical_path escapes root: {lp}")
        p = (root / lp).resolve()
        try:
            p.relative_to(root.resolve())
        except ValueError:
            raise SystemExit(f"REFUSED: path escapes ASSET_ROOT: {lp}")
        if not p.is_file():
            raise SystemExit(f"MISSING: {lp} under {root}")
        a["sha256"] = sha256(p)
        a["duration_s"] = duration(p)
        n += 1
    reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n")
    print(f"refreshed {n} assets in {reg_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
