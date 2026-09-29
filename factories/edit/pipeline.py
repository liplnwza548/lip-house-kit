#!/usr/bin/env python3
"""Edit factory pipeline (lip-house-kit): edit order in, base clip out.

Single entry: run_pipe(order: dict, workdir: Path) -> report dict.
Steps: validate order (hook + shots sum == target_dur) -> cut each part
(1080x1920, 30fps CFR, CRF18, no audio) -> concat -> verify duration.
Any mismatch raises SystemExit (fail loud).

Banned by house policy (DECISIONS 2026-09-25): zoompan d>1 on video
(freezes the first frame) — a vf containing 'zoompan' is refused loudly.

Order keys (schemas/edit-order.schema.json):
  hook: {file, trim?} | null, proxy, target_dur, shots: [{id, ss, d, note?}]

Import-safe: NOTHING runs on import.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} FAILED: {(p.stderr or '').strip()[-300:]}")
    return p


def duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)])
    return float(p.stdout.strip())


def cut(src, ss, d, out, vf="scale=1080:1920"):
    if "zoompan" in (vf or ""):
        raise SystemExit("EDIT_REFUSED: zoompan d>1 on video freezes frames "
                         "(house policy 2026-09-25) — use native motion cuts")
    run(["ffmpeg", "-y", "-v", "error", "-ss", str(ss), "-i", str(src),
         "-t", str(d), "-vf", vf or "scale=1080:1920", "-r", "30",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "18", "-an", str(out)])


def run_pipe(order, workdir):
    workdir = Path(workdir)
    parts_dir = workdir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    for key in ("proxy", "target_dur", "shots"):
        if key not in order:
            raise SystemExit(f"WORK_ORDER_REFUSED: missing key {key!r}")
    proxy = Path(order["proxy"])
    if not proxy.is_file():
        raise SystemExit(f"WORK_ORDER_REFUSED: proxy not found: {proxy}")
    target = float(order["target_dur"])
    shots = order["shots"] or []
    if not shots and not order.get("hook"):
        raise SystemExit("WORK_ORDER_REFUSED: empty edit (no hook, no shots)")
    planned = sum(float(s["d"]) for s in shots)
    hook_dur = 0.0
    hook = order.get("hook")
    if hook:
        hook_file = Path(hook["file"])
        if not hook_file.is_file():
            raise SystemExit(f"WORK_ORDER_REFUSED: hook not found: {hook_file}")
        hook_dur = float(hook.get("trim") or duration(hook_file))
    if abs(hook_dur + planned - target) > 0.15:
        raise SystemExit(
            f"WORK_ORDER_REFUSED: hook({hook_dur:.3f}) + shots({planned:.3f}) "
            f"= {hook_dur + planned:.3f}s != target {target:.3f}s")
    parts = []
    if hook:
        hpart = parts_dir / "hook.mp4"
        cut(hook["file"], 0, hook_dur, hpart)
        parts.append(hpart)
    for i, shot in enumerate(shots):
        for key in ("id", "ss", "d"):
            if key not in shot:
                raise SystemExit(f"WORK_ORDER_REFUSED: shot {i} lacks {key!r}")
        part = parts_dir / f"shot{i:02d}_{shot['id']}.mp4"
        cut(proxy, shot["ss"], shot["d"], part)
        parts.append(part)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write("".join(f"file '{p}'\n" for p in parts))
        lst = fh.name
    out = workdir / "base.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", str(out)])
    got = duration(out)
    if abs(got - target) > 0.15:
        raise SystemExit(f"EDIT_REFUSED: built {got:.3f}s != target "
                         f"{target:.3f}s")
    return {"ok": True, "out_mp4": str(out), "duration": round(got, 3),
            "parts": len(parts)}


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: pipeline.py <edit-order.json> <workdir>")
    order = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    report = run_pipe(order, Path(sys.argv[2]))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
