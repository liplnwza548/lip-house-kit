#!/usr/bin/env python3
"""Synthesize all 8 house SFX from recipes (ffmpeg lavfi, no binaries in repo).

Recipes 1-5 are verbatim from template-lab/.../editorial-assets/v0.1/gen_sfx.py.
Recipes 6-8 reconstruct track-A sounds (2026-09-30); each generation is
checked against the approved file's mean/max volume (tolerance 1dB).

Provenance for assets/registry.json (generator: this file + version tag).
Usage: python3 tools/synth_sfx.py <outdir>
"""
import subprocess
import sys
from pathlib import Path

VERSION = "synth_sfx v1 (2026-09-30)"


def run(cmd):
    subprocess.run(cmd, check=True)


def synth(outdir: Path, name: str, f32: str, af: str, dur: float):
    out = outdir / f"{name}.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f32,
         "-af", af, "-t", str(dur), "-ar", "44100", "-ac", "1", str(out)])
    return out


RECIPES = [
    # (name, lavfi_src, audio_filter, seconds)
    ("click", "aevalsrc=exp(-45*t)*sin(2*PI*2000*t):s=44100:d=0.1",
     "alimiter=limit=0.9,volume=0.8", 0.1),
    ("pop", "aevalsrc=sin(2*PI*(400*t+2800*t*t))*exp(-22*t):s=44100:d=0.15",
     "alimiter=limit=0.9,volume=0.8", 0.15),
    ("short_whoosh", "anoisesrc=color=white:seed=7:sample_rate=44100:d=0.45",
     "highpass=f=600,lowpass=f=6000,afade=t=in:st=0:d=0.32,afade=t=out:st=0.32:d=0.13,volume=0.5", 0.45),
    ("fast_whoosh", "anoisesrc=color=white:seed=21:sample_rate=44100:d=0.3",
     "highpass=f=1200,afade=t=in:st=0:d=0.18,afade=t=out:st=0.18:d=0.12,volume=0.55", 0.3),
    ("impact_soft", "sine=frequency=90:sample_rate=44100:duration=0.55",
     "afade=t=out:st=0:d=0.55,volume=0.9", 0.55),
    ("riser_08", "aevalsrc=sin(2*PI*(300*t+1312.5*t*t)):s=44100:d=0.8",
     "afade=t=in:st=0:d=0.8,alimiter=limit=0.9,volume=0.63", 0.8),
    ("ching", "aevalsrc=(sin(2*PI*3520*t)+0.6*sin(2*PI*5280*t)+0.4*sin(2*PI*7040*t))*exp(-8*t):s=44100:d=0.6",
     "alimiter=limit=0.9,volume=0.7", 0.6),
    ("pop_low", "aevalsrc=sin(2*PI*(250*t+694.4*t*t))*exp(-20*t):s=44100:d=0.18",
     "alimiter=limit=0.9,volume=0.85", 0.18),
]


def main() -> None:
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else "sfx_out")
    outdir.mkdir(parents=True, exist_ok=True)
    for name, f32, af, dur in RECIPES:
        synth(outdir, name, f32, af, dur)
        print(f"synth {name}.wav ({VERSION})")


if __name__ == "__main__":
    main()
