#!/usr/bin/env python3
"""Scout factory step 1 (deterministic): contact sheet + per-second metrics.

Input: raw/proxy footage. Output: contact sheet JPG + metrics CSV
(sharp/bright/motion per second) + shot_table skeleton CSV.
The JUDGMENT step (which seconds are A/B/C) stays human/agent work —
see RUNBOOK.md. This script only produces the evidence they judge from.

Usage:
    python3 make_contact.py <footage.mp4> <out_dir> [--fps 1] [--cols 6]
Provenance: same metrics as subtitle-work/footage/qa/shot_table.csv
(Laplacian sharpness, luma brightness, inter-frame motion).
"""
import csv
import subprocess
import sys
from pathlib import Path

import numpy as np


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} FAILED: {(p.stderr or '').strip()[-300:]}")
    return p


def duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)])
    return float(p.stdout.strip())


def gray_frame(path, ss, w=270, h=480):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(ss), "-i", str(path),
         "-frames:v", "1", "-vf", f"scale={w}:{h},format=gray",
         "-c:v", "rawvideo", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        capture_output=True)
    if p.returncode != 0 or not p.stdout:
        return None
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape((h, w))


def lap_var(g):
    gx = np.abs(g.astype(int)[:, 2:] - 2 * g.astype(int)[:, 1:-1]
                + g.astype(int)[:, :-2])
    gy = np.abs(g.astype(int)[2:, :] - 2 * g.astype(int)[1:-1, :]
                + g.astype(int)[:-2, :])
    return round(float(gx.var() + gy.var()), 1)


def main() -> int:
    args = sys.argv[1:]
    fps, cols = 1, 6
    files = []
    i = 0
    while i < len(args):
        if args[i] == "--fps" and i + 1 < len(args):
            fps, i = int(args[i + 1]), i + 2
        elif args[i] == "--cols" and i + 1 < len(args):
            cols, i = int(args[i + 1]), i + 2
        elif args[i].startswith("--"):
            raise SystemExit(f"unknown flag {args[i]}")
        else:
            files.append(args[i])
            i += 1
    if len(files) != 2:
        raise SystemExit("usage: make_contact.py <footage.mp4> <out_dir> "
                         "[--fps 1] [--cols 6]")
    src, out_dir = Path(files[0]), Path(files[1])
    assert src.is_file(), f"missing: {src}"
    thumbs = out_dir / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    dur = duration(src)
    rows = []
    prev = None
    saved = []
    t = 0.0
    while t < dur:
        g = gray_frame(src, t)
        if g is None:
            break
        motion = round(float(np.abs(g.astype(int) -
                                    prev.astype(int)).mean()), 1) \
            if prev is not None else 0.0
        prev = g
        rows.append({"t": round(t, 1), "sharp": lap_var(g),
                     "bright": round(float(g.mean()), 1), "motion": motion})
        thumb = thumbs / f"t{int(t):04d}.jpg"
        run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(src),
             "-frames:v", "1", "-vf", "scale=270:480", str(thumb)])
        saved.append(thumb)
        t += 1.0 / fps
    with open(out_dir / "metrics.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["t", "sharp", "bright",
                                                "motion"])
        writer.writeheader()
        writer.writerows(rows)
    with open(out_dir / "shot_table.csv", "w", newline="",
              encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["shot", "start", "end", "grade(A/B/C)", "role",
                         "note"])
        writer.writerow(["# ตัวอย่าง: เติมโดยคน/เอเจนต์หลังดู contact sheet",
                         "", "", "", "", ""])
    # Contact sheet grid (Pillow-free: ffmpeg tile, exact rows).
    import math
    pattern = str(thumbs / "t%04d.jpg")
    n_rows = max(1, math.ceil(len(saved) / cols))
    run(["ffmpeg", "-y", "-v", "error", "-framerate", "1", "-i", pattern,
         "-frames:v", "1",
         "-vf", f"scale=270:480,tile={cols}x{n_rows}",
         str(out_dir / "contact.jpg")])
    print(f"SCOUT_OK frames={len(saved)} metrics={len(rows)} "
          f"-> {out_dir}", flush=True)
    print("sharp>1000 ชัด / 400-1000 นุ่ม / <400 เบลอ (เกณฑ์คร่าว VM)",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
