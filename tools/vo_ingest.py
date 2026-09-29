#!/usr/bin/env python3
"""Canonical VO ingest (P1): normalize ONCE, every render pulls THIS file.

Principle (Lip-locked 2026-09-29): the same source VO rendered into any
number of clips must sound identical. Per-batch re-normalization broke
that (batch H02 stem -16.99 vs H03 stem -16.57 from identical bytes).

Flow: source.mov --extract--> vo_master.wav --two-pass loudnorm-->
vo_canonical.wav + manifest.json (SHA-256, LUFS, RMS, spectral centroid).

Usage:
    python3 vo_ingest.py <source.mov> <out_dir> [--target -17] [--name vo]
Output: <out_dir>/vo_canonical.wav + <out_dir>/manifest.json
Exit 2 when the verification readback misses target by more than 0.5 LU.

Import-safe: NOTHING runs on import.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} FAILED: {(p.stderr or '').strip()[-300:]}")
    return p


def ff_loudness(path):
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    text = p.stdout + p.stderr
    return json.loads(text[text.find("{"):text.rfind("}") + 1])


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def raw_mono(path, sr=44100):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
         "-c:a", "pcm_s16le", "-f", "s16le", "-"],
        capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("pcm extract failed")
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float64) / 32768.0


def spectral_centroid(path):
    """Mean frequency weighted by magnitude (50ms windows, voice band)."""
    x = raw_mono(path)
    sr = 44100
    win, hop = int(sr * 0.05), int(sr * 0.025)
    if len(x) < win:
        return 0.0
    freqs = np.fft.rfftfreq(win, 1 / sr)
    band = (freqs >= 80) & (freqs <= 12000)
    cents = []
    for start in range(0, len(x) - win, hop):
        mag = np.abs(np.fft.rfft(x[start:start + win] *
                                 np.hanning(win)))[band]
        if mag.sum() > 1e-9:
            cents.append(float((mag * freqs[band]).sum() / mag.sum()))
    active = [c for c in cents if c > 0]
    return round(sum(active) / len(active), 1) if active else 0.0


def rms_db(path):
    x = raw_mono(path)
    return round(float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12)), 2)


def ingest(source, out_dir, target=-17.0, name="vo"):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    master = out_dir / f"{name}_master.wav"
    canon = out_dir / "vo_canonical.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-map", "0:a",
         "-c:a", "pcm_s16le", "-ar", "44100", str(master)])
    m1 = ff_loudness(master)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(master),
         "-af", f"loudnorm=I={target}:TP=-3:LRA=11:"
                f"measured_I={m1['input_i']}:measured_TP={m1['input_tp']}:"
                f"measured_LRA={m1['input_lra']}:"
                f"measured_thresh={m1['input_thresh']}:offset=0:linear=true",
         "-ar", "44100", str(canon)])
    m2 = ff_loudness(canon)
    if abs(float(m2["input_i"]) - target) > 0.5:
        raise SystemExit(f"INGEST_REFUSED: {m2['input_i']} LUFS vs "
                         f"target {target}")
    manifest = {
        "source": str(source), "source_sha256": sha256(source),
        "canonical": canon.name, "canonical_sha256": sha256(canon),
        "target_lufs": target,
        "lufs": float(m2["input_i"]), "true_peak_dbtp": float(m2["input_tp"]),
        "rms_dbfs": rms_db(canon), "spectral_centroid_hz":
            spectral_centroid(canon),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"INGEST_OK {canon.name}: {manifest['lufs']} LUFS, "
          f"TP {manifest['true_peak_dbtp']} dBTP, RMS {manifest['rms_dbfs']} "
          f"dBFS, centroid {manifest['spectral_centroid_hz']} Hz",
          flush=True)
    print(f"MANIFEST {out_dir / 'manifest.json'}", flush=True)
    return manifest


def main() -> int:
    args = sys.argv[1:]
    target = -17.0
    name = "vo"
    files = []
    i = 0
    while i < len(args):
        if args[i] == "--target" and i + 1 < len(args):
            target, i = float(args[i + 1]), i + 2
        elif args[i] == "--name" and i + 1 < len(args):
            name, i = args[i + 1], i + 2
        elif args[i].startswith("--"):
            raise SystemExit(f"unknown flag {args[i]}")
        else:
            files.append(args[i])
            i += 1
    if len(files) != 2:
        raise SystemExit("usage: vo_ingest.py <source.mov> <out_dir> "
                         "[--target -17] [--name vo]")
    ingest(files[0], files[1], target, name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
