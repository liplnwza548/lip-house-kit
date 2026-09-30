#!/usr/bin/env python3
"""Validate assets/registry.json against the schema + real files.

Pure function `validate(registry, asset_root) -> list[str]` (no globals,
fresh error list every call). CLI reads ASSET_ROOT inside main() — never at
import — and refuses to guess a machine default.

Fails LOUD when: schema invalid, file missing, SHA mismatch, license
evidence incomplete, asset unapproved, duplicate ID, or path escapes root.

Usage: ASSET_ROOT=/path/to/assets python3 tools/validate_registry.py
"""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schemas" / "asset-registry.schema.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def schema_errors(reg: dict) -> list:
    """Validate shape with the real JSON schema (Draft 2020-12)."""
    import jsonschema
    schema = json.loads(SCHEMA_PATH.read_text())
    problems = []
    validator = jsonschema.Draft202012Validator(schema)
    for e in validator.iter_errors(reg):
        where = "/" + "/".join(str(p) for p in e.absolute_path)
        problems.append(f"schema{where or '/'}: {e.message[:160]}")
    return problems


def validate(reg: dict, asset_root: Path) -> list:
    errors: list = []
    errors.extend(schema_errors(reg))
    assets = reg.get("assets")
    if not isinstance(assets, list):
        return errors + ["'assets' must be a list"]
    seen = set()
    for i, a in enumerate(assets):
        if not isinstance(a, dict):
            errors.append(f"index#{i}: entry is not an object ({type(a).__name__})")
            continue
        tag = a.get("asset_id", f"index#{i}")
        if tag in seen:
            errors.append(f"{tag}: DUPLICATE asset_id")
        seen.add(tag)
        if not a.get("approved"):
            errors.append(f"{tag}: NOT APPROVED (approved=false)")
        for k in ("license_name", "license_evidence", "source_url"):
            if not a.get(k):
                errors.append(f"{tag}: incomplete license evidence ('{k}' empty)")
        if a.get("kind") == "bgm" and not a.get("commercial_use"):
            errors.append(f"{tag}: bgm not cleared for commercial use")
        lp = a.get("logical_path", "")
        if not isinstance(lp, str) or not lp or lp.startswith("/") or ".." in Path(lp).parts:
            errors.append(f"{tag}: logical_path '{lp}' must be relative inside ASSET_ROOT")
            continue
        real = (asset_root / lp).resolve()
        try:
            real.relative_to(asset_root.resolve())
        except ValueError:
            errors.append(f"{tag}: path escapes ASSET_ROOT: {lp}")
            continue
        if not real.is_file():
            errors.append(f"{tag}: FILE MISSING: {lp} (ASSET_ROOT={asset_root})")
            continue
        if real.suffix.lower() in (".mp3", ".wav", ".ogg", ".flac", ".m4a"):
            actual = sha256(real)
            if actual != a.get("sha256"):
                errors.append(f"{tag}: SHA MISMATCH for {lp}\n  registry: {a.get('sha256')}\n  actual:   {actual}")
    return errors


def main(asset_root=None) -> int:
    raw = asset_root or os.environ.get("ASSET_ROOT")
    if not raw:
        print("ASSET_ROOT is not set — point it at your media folder, e.g.\n"
              "  ASSET_ROOT=/home/box/subtitle-work/assets (VM)\n"
              "  $env:ASSET_ROOT='D:\\lip-assets' (Windows)")
        return 2
    root = Path(raw)
    reg_path = ROOT / "assets" / "registry.json"
    try:
        reg = json.loads(reg_path.read_text())
    except Exception as e:
        print(f"REGISTRY_UNREADABLE: {e}")
        return 2
    errors = validate(reg, root)
    if errors:
        print(f"REGISTRY_INVALID: {len(errors)} problem(s) (ASSET_ROOT={root})")
        for e in errors:
            print(" -", e)
        return 1
    print(f"REGISTRY_OK: {len(reg['assets'])} assets approved+verified (ASSET_ROOT={root})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
