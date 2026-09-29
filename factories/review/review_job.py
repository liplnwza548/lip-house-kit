#!/usr/bin/env python3
"""Review factory: AGY watches the video, Lip decides. (Never reversed.)

Proven 2026-09-30 (C1 test): AGY demuxes audio, runs STT, inspects frames,
cross-checks an existing script, and reports line diffs with confidence.
HARD LIMITS (tested): AGY cannot truly hear (it reads transcripts), it
overstates confidence (claimed 99% while siding with ขากระบอก against
Lip's locked ขาสั้น), so it must NEVER lock wording. Its job is PREP:
numbered draft lines + uncertain list + evidence. Lip's reply locks.

Usage:
    python3 review_job.py <video.mp4> <out_dir> [--script locked.txt]
Output: <out_dir>/review.json:
    {"lines": [...], "uncertain": [{"line": n, "options": [...], "why": ...}],
     "confidence": n, "method": "..."}
The uncertain list uses the Cn protocol: Lip replies
"Cn ข้อม: <true sentence>" per fix, or "Cn โอเค".

Import-safe: NOTHING runs on import. Needs: ffmpeg + agy CLI.
"""
import json
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd=None):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} FAILED: {(p.stderr or '').strip()[-300:]}")
    return p


PROMPT = """งานตรวจวิดีโอเพื่องานซับ ตอบภาษาไทย ห้ามรันคำสั่งลบ
ไฟล์วิดีโอ: {video}
{script_brief}
ทำ 4 อย่าง:
1) ดึงเสียงมาตรวจโครงสร้าง (ffprobe + แยกเสียง) แล้วถอดเสียงพากษ์เป็นบทพูดทีละท่อนพร้อมเวลาคร่าวๆ (ใช้ Groq/Typhoon ตามที่มี หรออ่านไฟล์ asr เดิมถ้ามีในโฟลเดอร์งาน)
2) แคปเฟรมทุก ~5 วินาทีมาดูบริบทสินค้า (สินค้าอะไร ทำอะไรในภาพ) ประกอบการแก้คำฟังผิด
3) ส่งบทดิบครบทุกท่อน + รายการจุดไม่แน่ใจแยกข้อ (ตัวเลือก ก/ข + เหตุผล) + ระดับความมั่นใจรวมเป็นเปอร์เซ็นต์แบบซื่อสัตย์ (ห้ามตอบ 99% ถ้าไม่ได้ยินเสียงเอง — บอกตามตรงว่าเป็นการอ่าน transcript)
4) กฎเหล็ก: ห้ามแต่งประโยคใหม่ ห้ามเติม/ตัดคำ ห้ามฟันธงคำยืมหรือคำปฏิเสธ — ใส่ธงให้เจ้าของเสียงชี้ขาด"""


def main() -> int:
    args = sys.argv[1:]
    script = None
    files = []
    i = 0
    while i < len(args):
        if args[i] == "--script" and i + 1 < len(args):
            script, i = args[i + 1], i + 2
        elif args[i].startswith("--"):
            raise SystemExit(f"unknown flag {args[i]}")
        else:
            files.append(args[i])
            i += 1
    if len(files) != 2:
        raise SystemExit("usage: review_job.py <video.mp4> <out_dir> "
                         "[--script locked.txt]")
    video, out_dir = Path(files[0]), Path(files[1])
    assert video.is_file(), f"missing: {video}"
    if script is not None:
        assert Path(script).is_file(), f"missing script: {script}"
    out_dir.mkdir(parents=True, exist_ok=True)
    brief = (f"มีบทตั้งต้นแนบที่ {script} ช่วยเทียบว่าตรงเสียงไหม "
             f"ท่อนไหนต่างให้แยกธง" if script
             else "ไม่มีบทตั้งต้น ถอดจากเสียงล้วน")
    prompt = PROMPT.format(video=video.resolve(), script_brief=brief)
    last = None
    report = None
    for attempt in range(1, 4):
        p = subprocess.run(
            ["timeout", "550", "agy", "--dangerously-skip-permissions",
             "-p", prompt], capture_output=True, text=True,
            cwd=str(out_dir))
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode == 0 and len(out.strip()) > 200:
            report = out.strip()
            break
        last = out.strip()[-300:]
        print(f"AGY attempt {attempt} inconclusive, retrying...", flush=True)
    if report is None:
        raise SystemExit(f"REVIEW_FAILED after 3 tries. Last: {last}")
    (out_dir / "review_raw.txt").write_text(report + "\n", encoding="utf-8")
    print(f"REVIEW_OK -> {out_dir / 'review_raw.txt'} "
          f"({len(report)} chars)", flush=True)
    print("NEXT: Lip อ่าน uncertain list แล้วตอบ Cn ข้อม:/Cn โอเค — "
          "AGY ไม่มีสิทธิ์ล็อกบท", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
