#!/usr/bin/env python3
"""Batch QA frames: extract stills at check timestamps, ask AGY to verify.

Replaces the hand-driven loop from client-batch1/batch2 (ffmpeg stills +
pasted AGY prompts + manual verdict reading).

Checks file (JSON list):
    [{"label": "c4_502", "t": 5.30, "expect": "กระเป๋าใบนี้ช่วย",
      "yellow": null},
     {"label": "c2_531", "t": 5.38, "expect": "ใบโปรดไปแล้ว",
      "yellow": "ใบโปรด"}]
- t: seconds into VIDEO (the final mixed file).
- expect: exact subtitle text that must be on screen.
- yellow: word that must be yellow (null = no yellow required).

Usage:
    python3 qa_batch.py <video.mp4> <checks.json> <out_dir> [--retries 3]

Writes <out_dir>/frames/*.png + <out_dir>/qa_report.txt (AGY raw output).
Exit 0 when AGY answers; exit 2 when AGY keeps failing after retries
(frames are still on disk for manual review). AGY verdicts are recorded,
not trusted blindly — a human still reads qa_report.txt before delivery.

Import-safe: NOTHING runs on import.
"""
import json
import subprocess
import sys
from pathlib import Path


def extract_frames(video, checks, frames_dir):
    frames_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for check in checks:
        out = frames_dir / f"{check['label']}.png"
        p = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(check["t"]),
             "-i", str(video), "-frames:v", "1", str(out)],
            capture_output=True, text=True)
        if p.returncode != 0 or not out.is_file():
            raise RuntimeError(f"frame extract failed for {check['label']}: "
                               f"{(p.stderr or '').strip()[-200:]}")
        saved.append(out)
    return saved


def build_prompt(checks):
    lines = ["ตรวจเฟรมซับไตเติล ตอบภาษาไทย ใบละ 2-3 บรรทัด "
             "ห้ามรันคำสั่งลบ"]
    for check in checks:
        line = (f"ดูภาพ @{check['label']}.png ข้อความที่ต้องเห็นคือ "
                f"{check['expect']}")
        if check.get("yellow"):
            line += f" คำที่ต้องเป็นสีเหลืองคือ {check['yellow']}"
        line += (" ถ้าตรงให้จบด้วย PASS ถ้าไม่ตรงให้บอกว่าเห็นอะไรแล้วจบ "
                 "ด้วย FAIL พร้อมบอกว่ามี tofu ล้นขอบ หรือซ้อนบรรทัดหรือไม่")
        lines.append(line)
    return " ".join(lines)


def ask_agy(prompt, workdir, retries=3):
    last = None
    for attempt in range(1, retries + 1):
        p = subprocess.run(
            ["timeout", "240", "agy", "--dangerously-skip-permissions",
             "-p", prompt],
            capture_output=True, text=True, cwd=str(workdir))
        out = (p.stdout or "") + (p.stderr or "")
        tail = "\n".join(out.strip().splitlines()[-40:])
        if p.returncode == 0 and ("PASS" in tail or "FAIL" in tail):
            return tail, attempt
        last = tail[-500:]
        print(f"AGY attempt {attempt} inconclusive, retrying...", flush=True)
    raise RuntimeError(f"AGY gave no verdict after {retries} tries. "
                       f"Last output: {last}")


def main() -> int:
    if len(sys.argv) < 4:
        raise SystemExit("usage: qa_batch.py <video.mp4> <checks.json> "
                         "<out_dir> [--retries N]")
    video = Path(sys.argv[1])
    checks = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    out_dir = Path(sys.argv[3])
    retries = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[4] == "--retries" else 3
    assert video.is_file(), f"video not found: {video}"
    assert checks, "empty checks list"
    frames = extract_frames(video, checks, out_dir / "frames")
    print(f"FRAMES {len(frames)} saved to {out_dir / 'frames'}", flush=True)
    report, attempt = ask_agy(build_prompt(checks), out_dir / "frames",
                              retries)
    (out_dir / "qa_report.txt").write_text(report + "\n", encoding="utf-8")
    print(f"QA_REPORT attempt={attempt} -> {out_dir / 'qa_report.txt'}",
          flush=True)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
