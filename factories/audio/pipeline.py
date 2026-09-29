#!/usr/bin/env python3
"""Audio factory pipeline (lip-house-kit): canonical VO + clip + bed in,
mastered final out.

Single entry: run_pipe(order: dict, workdir: Path) -> report dict.
Steps: validate manifest SHA -> mux canonical VO under video (apad to
video length) -> fixed-gain mix (+optional SFX bus) -> verify gates.
Any gate breach raises SystemExit (fail loud, file kept for forensics
but NOT deliverable).

Order keys: video, vo_canonical, manifest, bgm_track, sfx_bus?,
level_db?=-20, makeup_db?=1.0, deliver?

Import-safe: NOTHING runs on import.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".." / "tools"))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"ffprobe failed on {path}")
    return float(p.stdout.strip())


def run_pipe(order, workdir):
    from mix_bgm import mix
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    for key in ("video", "vo_canonical", "manifest", "bgm_track"):
        if key not in order:
            raise SystemExit(f"WORK_ORDER_REFUSED: missing key {key!r}")
    video = Path(order["video"])
    vo = Path(order["vo_canonical"])
    manifest = json.loads(Path(order["manifest"]).read_text(encoding="utf-8"))
    if sha256(vo) != manifest.get("canonical_sha256"):
        raise SystemExit("MANIFEST_MISMATCH: vo_canonical.wav bytes differ "
                         "from manifest — re-ingest, never burn on drift")
    vdur = duration(video)
    laid = workdir / "vo_laid.mp4"
    p = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(vo),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-af", f"apad=whole_dur={vdur:.2f}", "-c:a", "aac", "-b:a", "192k",
         "-t", f"{vdur:.2f}", str(laid)], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"VO_LAY_FAILED: {p.stderr[-300:]}")
    out = workdir / f"{video.stem}_final.mp4"
    mix(laid, order["bgm_track"], out,
        level_db=float(order.get("level_db", -20.0)),
        fixed_gain=True, sfx=order.get("sfx_bus"),
        verify_against=str(vo), makeup_db=float(order.get("makeup_db", 1.0)))
    return {"ok": True, "out_mp4": str(out), "manifest_lufs":
            manifest.get("lufs")}


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: pipeline.py <audio-order.json> <workdir>")
    order = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    report = run_pipe(order, Path(sys.argv[2]))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
