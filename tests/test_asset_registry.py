"""Asset registry tests: positive vs real files + loud negative cases."""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

REG = ROOT / "assets" / "registry.json"


def run_validator(asset_root, reg_override=None):
    env = dict(os.environ, ASSET_ROOT=str(asset_root))
    if reg_override is not None:
        import validate_registry as vr
        orig = vr.REG
        vr.REG = Path(reg_override)
        try:
            code = vr.main()
            return code, "\n".join(vr.ERRORS)
        finally:
            vr.REG = orig
            vr.ERRORS.clear()
    p = subprocess.run([sys.executable, str(ROOT / "tools" / "validate_registry.py")],
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout + p.stderr


def test_registry_positive(tmp_path=None):
    import validate_registry as vr
    vr.ERRORS.clear()
    code = vr.main()
    assert code == 0, f"validator failed on real files: {vr.ERRORS}"
    assert len(json.loads(REG.read_text())["assets"]) == 13


def _mutated(tmp_path, fn):
    import tempfile
    reg = json.loads(REG.read_text())
    fn(reg)
    f = Path(tempfile.mkdtemp()) / "registry.json"
    f.write_text(json.dumps(reg))
    return str(f)


def test_negative_missing_file(tmp_path):
    import validate_registry as vr
    vr.ERRORS.clear()
    code, out = run_validator("/nonexistent-root-xyz")
    assert code == 1 and "FILE MISSING" in out


def test_negative_sha_mismatch(tmp_path):
    def fn(reg):
        reg["assets"][0]["sha256"] = "0" * 64
    code, out = run_validator(os.environ.get("ASSET_ROOT", "/home/box/subtitle-work/assets"),
                              _mutated(tmp_path, fn))
    assert code == 1 and "SHA MISMATCH" in out


def test_negative_duplicate_id(tmp_path):
    def fn(reg):
        reg["assets"].append(copy.deepcopy(reg["assets"][0]))
    code, out = run_validator(os.environ.get("ASSET_ROOT", "/home/box/subtitle-work/assets"),
                              _mutated(tmp_path, fn))
    assert code == 1 and "DUPLICATE" in out


def test_negative_license_gap(tmp_path):
    def fn(reg):
        reg["assets"][1]["license_evidence"] = ""
    code, out = run_validator(os.environ.get("ASSET_ROOT", "/home/box/subtitle-work/assets"),
                              _mutated(tmp_path, fn))
    assert code == 1 and "license" in out.lower()


def test_negative_path_escape(tmp_path):
    def fn(reg):
        reg["assets"][2]["logical_path"] = "../outside.mp3"
    code, out = run_validator(os.environ.get("ASSET_ROOT", "/home/box/subtitle-work/assets"),
                              _mutated(tmp_path, fn))
    assert code == 1 and ("escapes" in out or "relative" in out)
