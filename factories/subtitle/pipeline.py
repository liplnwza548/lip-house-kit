#!/usr/bin/env python3
"""Subtitle factory pipeline (lip-house-kit): work order in, subtitled clip out.

Single entry: run_pipe(order: dict, workdir: Path) -> report dict.
Steps: validate order -> timing (cached words_json or live stt_guard) ->
align/gate -> keyword coverage -> split/trim/merge/auto_repair ->
validate/assert_fit -> burn. Any leftover or refusal raises SystemExit
(fail loud, writes nothing half-done).

Work order keys (schemas/work-order.schema.json):
  clip, script, keywords?, profile?=vo, words_json?, deliver?

Import-safe: NOTHING runs on import.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "renderer" / "render"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".." / "tools"))


def run_pipe(order, workdir):
    from script_align import align_script_to_timeline
    from script_autorepair import auto_repair
    from script_burn import burn_script_aligned
    from script_gate import gate_before_burn
    from script_keywords import check_keyword_hits
    from script_marks import validate_final_cues
    from script_pipeline import load_script_lines, load_words_json, resolve_keywords
    from script_split import split_alignment
    from script_timing import merge_short_cues, trim_overlaps
    from script_width import assert_fit

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    for key in ("clip", "script"):
        if key not in order:
            raise SystemExit(f"WORK_ORDER_REFUSED: missing key {key!r}")
    clip = Path(order["clip"])
    script = Path(order["script"])
    if not clip.is_file():
        raise SystemExit(f"WORK_ORDER_REFUSED: clip not found: {clip}")
    if not script.is_file():
        raise SystemExit(f"WORK_ORDER_REFUSED: script not found: {script}")
    profile = order.get("profile", "vo")
    keywords = resolve_keywords(order.get("keywords"), None)
    # Timing: cached words JSON, else live guarded STT on a proxy wav.
    if order.get("words_json"):
        words = load_words_json(Path(order["words_json"]))
    else:
        from stt_guard import transcribe_guarded
        wav = workdir / "proxy16k.wav"
        p = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", str(clip), "-ac", "1", "-ar", "16000", str(wav)],
            capture_output=True, text=True)
        if p.returncode != 0:
            raise SystemExit(f"STT_BLOCKED: proxy wav failed: "
                             f"{p.stderr[-200:]}")
        words = transcribe_guarded(wav)["data"]
    lines = load_script_lines(script)
    alignment = align_script_to_timeline(lines, words)
    gate = gate_before_burn(alignment)
    if not gate["ok"]:
        raise SystemExit(f"GATE_BLOCKED: {gate['report'][:500]}")
    if keywords:
        hits = check_keyword_hits(lines, keywords)
        missing = [k for k, c in hits.items() if c == 0]
        if missing:
            raise SystemExit(f"KEYWORD_COVERAGE_REFUSED: 0 hits: {missing}")
    alignment = split_alignment(alignment, words=words, keywords=keywords)
    matched = trim_overlaps(alignment["matched"])
    merged, merge_rep = merge_short_cues(
        matched, min_duration=0.5, max_width_px=None, max_syl=8,
        allow_cross_line=False)
    final_matched, auto_rep = auto_repair(merged, words)
    if auto_rep["leftover"]:
        raise SystemExit(f"REPAIR_LEFTOVER (needs hand table or Lip "
                         f"exception): {auto_rep['leftover']}")
    final = validate_final_cues(final_matched, keywords, None,
                                profile=profile)
    assert_fit(final_matched)
    fonts = Path(__file__).resolve().parents[1] / ".." / "glossary"
    out = workdir / f"{clip.stem}_subtitled.mp4"
    result = burn_script_aligned(
        clip, {"matched": final_matched, "mismatches": []}, fonts, out,
        keywords=keywords, profile=profile)
    return {"ok": True, "out_mp4": str(result.get("out_mp4", out)),
            "cues": len(final_matched),
            "merged": merge_rep["merged"],
            "repaired": auto_rep["repaired"],
            "warnings": final["warnings"] + alignment.get("warnings", [])}


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: pipeline.py <work-order.json> <workdir>")
    order = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    report = run_pipe(order, Path(sys.argv[2]))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
