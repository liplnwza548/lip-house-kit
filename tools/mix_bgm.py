#!/usr/bin/env python3
"""Shared BGM mix for subtitled clips (house recipe, batch-agnostic).

Bed under the clip's own audio: looped/trimmed track at --level dB with
1s fades, ducked under VO via sidechaincompress keyed on the clip audio,
mixed back with normalize=0 (calibrated gains survive), single-pass
loudnorm to the house target (-15 LUFS). Prints a loudness readback per
file (dual-pass measure, no second encode).

Usage:
    python3 mix_bgm.py --track <bgm.mp3> [--level -20] [--outdir DIR]
                       [--target -15] <clip1.mp4> [clip2.mp4 ...]
Output: <outdir>/<stem>_final.mp4 (default outdir = clips' own dir).

Provenance: generalized from client-batch2/mix_batch2.py (2026-09-29,
corporate bed -20dB, finals measured -15 LUFS +/-0.2).

Import-safe: NOTHING runs on import.
"""
import json
import subprocess
import sys
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


def loudness(path):
    """Measure integrated LUFS + true peak via loudnorm JSON (no encode)."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    text = p.stdout + p.stderr
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}


def mix(src, track, out, level_db=-20.0, target_lufs=-15.0,
        fixed_gain=False, sfx=None, verify_against=None, makeup_db=0.0):
    dur = duration(src)
    duck = (f"[1:a]atrim=0:{dur:.2f},asetpts=PTS-STARTPTS,"
            f"volume={level_db}dB,afade=t=in:st=0:d=1,"
            f"afade=t=out:st={dur - 1:.2f}:d=1[bg];"
            f"[bg][0:a]sidechaincompress=threshold=0.015:ratio=8:"
            f"attack=15:release=400[duck];")
    if fixed_gain:
        # P2 fixed-gain chain (Lip-locked 2026-09-29): VO passes at unity,
        # NOTHING dynamic touches it; bed is relative; a transparent TP
        # limiter guards clipping only. Master lands where fixed gains put
        # it — the gate below VERIFIES instead of auto-correcting, so two
        # clips from one canonical stem mix bit-comparably by construction.
        # --makeup adds a FIXED linear gain (content-independent, invariance
        # safe) to center the recipe's deterministic landing on target.
        makeup = f",volume={makeup_db}dB" if makeup_db else ""
        if sfx is not None:
            fc = (duck + f"[0:a][duck][2:a]amix=inputs=3:duration=first:"
                  f"dropout_transition=0:normalize=0,"
                  f"alimiter=limit=0.891:attack=5:release=50{makeup}[aout]")
            inputs = ["-i", str(src), "-stream_loop", "-1", "-i", str(track),
                      "-i", str(sfx)]
        else:
            fc = (duck + f"[0:a][duck]amix=inputs=2:duration=first:"
                  f"dropout_transition=0:normalize=0,"
                  f"alimiter=limit=0.891:attack=5:release=50{makeup}[aout]")
            inputs = ["-i", str(src), "-stream_loop", "-1", "-i", str(track)]
    else:
        fc = (duck + f"[0:a][duck]amix=inputs=2:duration=first:"
              f"dropout_transition=0:normalize=0,"
              f"loudnorm=I={target_lufs}:TP=-1:LRA=11[aout]")
        inputs = ["-i", str(src), "-stream_loop", "-1", "-i", str(track)]
    run(["ffmpeg", "-y", "-v", "error"] + inputs +
        ["-filter_complex", fc, "-map", "0:v", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)])
    d2 = duration(out)
    meas = loudness(out)
    lufs = meas.get("input_i", "?")
    tp = meas.get("input_tp", "?")
    print(f"MIXED_OK {Path(out).name}: dur {d2:.2f}s "
          f"(drift {d2 - dur:+.3f}s) | {lufs} LUFS, TP {tp} dBTP",
          flush=True)
    if verify_against is not None:
        gate_report = verify_mix(out, verify_against, target_lufs)
        print(gate_report, flush=True)
    return out


def _mean_volume(path, start=0.0, length=None):
    args = ["ffmpeg", "-hide_banner"]
    if start:
        args += ["-ss", str(start)]
    args += ["-i", str(path)]
    if length:
        args += ["-t", str(length)]
    args += ["-af", "volumedetect", "-f", "null", "/dev/null"]
    p = subprocess.run(args, capture_output=True, text=True)
    for line in (p.stdout + p.stderr).splitlines():
        if "mean_volume" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0])
    raise RuntimeError("volumedetect gave no mean_volume")


def verify_mix(out, canonical_wav, target_lufs=-15.0):
    """P3 gate: master window + speech-region match + centroid drift.

    Raises SystemExit(2) on breach (fail loud, file stays for forensics
    but must NOT be delivered). Tolerances: master target +/-1.0;
    speech-region mean vs canonical stem within BED_LIFT_NOMINAL +/-1.5dB
    (the ducked bed audibly lifts the mixed region ~+2dB over the dry stem
    — calibrated 2026-09-29: both chain2 finals measured exactly +2.0dB);
    centroid drift +/-10%.
    """
    BED_LIFT_NOMINAL = 2.0
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from vo_ingest import spectral_centroid, raw_mono  # noqa: E402
    import numpy as np  # noqa: E402

    fails = []
    meas = loudness(out)
    try:
        master = float(meas["input_i"])
    except (KeyError, TypeError, ValueError):
        raise SystemExit("GATE_REFUSED: loudness unreadable")
    if abs(master - target_lufs) > 1.0:
        fails.append(f"master {master} LUFS outside {target_lufs}+/-1")
    vo_dur = duration(canonical_wav)
    stem_mean = _mean_volume(canonical_wav)
    mix_mean = _mean_volume(out, 0.0, vo_dur)
    lift = mix_mean - stem_mean
    if abs(lift - BED_LIFT_NOMINAL) > 1.5:
        fails.append(f"speech-region lift {lift:+.1f}dB vs nominal "
                     f"+{BED_LIFT_NOMINAL}dB (stem {stem_mean}dB, mix "
                     f"{mix_mean}dB — VO chain was touched)")
    stem_cent = spectral_centroid(canonical_wav)
    x = raw_mono(out)[:int(44100 * vo_dur)]
    sr = 44100
    win, hop = int(sr * 0.05), int(sr * 0.025)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    band = (freqs >= 80) & (freqs <= 12000)
    cents = []
    for start in range(0, max(len(x) - win, 1), hop):
        mag = np.abs(np.fft.rfft(x[start:start + win] * np.hanning(win)))[band]
        if mag.sum() > 1e-9:
            cents.append(float((mag * freqs[band]).sum() / mag.sum()))
    mix_cent = round(sum(cents) / len(cents), 1) if cents else 0.0
    drift = abs(mix_cent - stem_cent) / stem_cent if stem_cent else 0
    if drift > 0.10:
        fails.append(f"centroid {mix_cent}Hz vs stem {stem_cent}Hz "
                     f"(drift {drift:.1%} > 10%)")
    summary = (f"GATE master={master} speech={mix_mean}dB(stem {stem_mean}dB) "
               f"centroid={mix_cent}Hz(stem {stem_cent}Hz)")
    if fails:
        raise SystemExit("GATE_REFUSED: " + "; ".join(fails) + " | " + summary)
    return "GATE_PASS: " + summary


def main() -> int:
    args = sys.argv[1:]
    track, level, outdir, target = None, -20.0, None, -15.0
    fixed_gain, sfx, verify, makeup = False, None, None, 0.0
    files = []
    i = 0
    while i < len(args):
        if args[i] == "--track" and i + 1 < len(args):
            track, i = args[i + 1], i + 2
        elif args[i] == "--level" and i + 1 < len(args):
            level, i = float(args[i + 1]), i + 2
        elif args[i] == "--outdir" and i + 1 < len(args):
            outdir, i = args[i + 1], i + 2
        elif args[i] == "--target" and i + 1 < len(args):
            target, i = float(args[i + 1]), i + 2
        elif args[i] == "--fixed-gain":
            fixed_gain, i = True, i + 1
        elif args[i] == "--sfx" and i + 1 < len(args):
            sfx, i = args[i + 1], i + 2
        elif args[i] == "--verify" and i + 1 < len(args):
            verify, i = args[i + 1], i + 2
        elif args[i] == "--makeup" and i + 1 < len(args):
            makeup, i = float(args[i + 1]), i + 2
        elif args[i].startswith("--"):
            raise SystemExit(f"unknown flag {args[i]}")
        else:
            files.append(args[i])
            i += 1
    if not track or not files:
        raise SystemExit("usage: mix_bgm.py --track <bgm.mp3> "
                         "[--level -20] [--outdir DIR] [--target -15] "
                         "[--fixed-gain] [--sfx bus.wav] [--verify vo.wav] "
                         "[--makeup dB]<clip1.mp4> [...]")
    for clip in files:
        src = Path(clip)
        assert src.is_file(), f"missing: {src}"
        out = (Path(outdir) if outdir else src.parent) / f"{src.stem}_final.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            mix(src, track, out, level, target, fixed_gain, sfx, verify,
                makeup)
        except Exception as e:  # noqa: BLE001
            print(f"MIX_FAILED {src.name}: {type(e).__name__}: {e}",
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
