#!/usr/bin/env python3
"""QA/delivery factory (6th): final file in, verdict + optional delivery out.

Single entry: run_pipe(order: dict, workdir: Path) -> report dict.
Steps: frames at checks (tools/qa_batch) -> AGY verdict (PASS/FAIL per
frame, report saved) -> loudness window [-16,-14] + audio-stream check ->
optional Drive upload (--deliver FOLDER_ID; default OFF, report only).
Any FAIL/BLOCK raises SystemExit (fail loud, nothing delivered).

Order keys: final, checks (checks.json), deliver?=null|folder_id.

Import-safe: NOTHING runs on import. Needs: ffmpeg + agy CLI (+ Chrome
CDP 9225 with Drive login only when deliver is set).
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".." / "tools"))


def duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"ffprobe failed on {path}")
    return float(p.stdout.strip())


def loudness(path):
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    text = p.stdout + p.stderr
    try:
        return json.loads(text[text.find("{"):text.rfind("}") + 1])
    except ValueError:
        return {}


def has_audio(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    return bool((p.stdout or "").strip())


def run_pipe(order, workdir):
    from qa_batch import ask_agy, build_prompt, extract_frames
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    for key in ("final", "checks"):
        if key not in order:
            raise SystemExit(f"WORK_ORDER_REFUSED: missing key {key!r}")
    final = Path(order["final"])
    if not final.is_file():
        raise SystemExit(f"WORK_ORDER_REFUSED: final not found: {final}")
    checks = json.loads(Path(order["checks"]).read_text(encoding="utf-8"))
    frames = extract_frames(final, checks, workdir / "frames")
    report, attempt = ask_agy(build_prompt(checks), workdir / "frames", 3)
    (workdir / "qa_report.txt").write_text(report + "\n", encoding="utf-8")
    fails = report.count("FAIL")
    passes = report.count("PASS")
    if fails > 0 or passes == 0:
        raise SystemExit(f"QA_REFUSED: {passes} PASS / {fails} FAIL — "
                         f"see {workdir / 'qa_report.txt'}")
    if not has_audio(final):
        raise SystemExit("QA_REFUSED: final has no audio stream")
    try:
        lufs = float(loudness(final)["input_i"])
    except (KeyError, TypeError, ValueError):
        raise SystemExit("QA_REFUSED: loudness unreadable")
    if not (-16.0 <= lufs <= -14.0):
        raise SystemExit(f"QA_REFUSED: {lufs} LUFS outside -15+/-1")
    result = {"ok": True, "passes": passes, "lufs": lufs,
              "duration": round(duration(final), 2),
              "report": str(workdir / "qa_report.txt"), "delivered": None}
    if order.get("deliver"):
        from drive_upload import main as _upload_main  # noqa: E402
        folder = order["deliver"]
        saved_argv = sys.argv
        sys.argv = ["drive_upload.py", "--folder", folder, "--outdir",
                    str(final.parent), "--evidence", str(workdir / "upload"),
                    final.name]
        try:
            _upload_main()
        finally:
            sys.argv = saved_argv
        result["delivered"] = folder
    return result


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: pipeline.py <qa-order.json> <workdir>")
    order = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    report = run_pipe(order, Path(sys.argv[2]))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
