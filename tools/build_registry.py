#!/usr/bin/env python3
"""Build assets/registry.json from real files under ASSET_ROOT.

Measures sha256 + duration with tools on this machine; every descriptive
field is Lip-approved metadata written below (never guessed from audio).
bpm=null everywhere: no tempo meter on this VM (rule: leave blank, not guess).

Usage: ASSET_ROOT=/home/box/subtitle-work/assets python3 tools/build_registry.py
Writes: assets/registry.json
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_ROOT = Path(os.environ.get("ASSET_ROOT", "/home/box/subtitle-work/assets"))
OUT = ROOT / "assets" / "registry.json"

BGM = [
    dict(id="piano-corporate-482783", file="bgm/piano-corporate-482783.mp3",
         title="Corporate Piano - Uplifting Moments", artist="Sonican",
         source="https://pixabay.com/music/corporate-corporate-piano-uplifting-moments-482783",
         license="Pixabay Content License",
         evidence="subtitle-work/assets/bgm/README.md + page URL above",
         mood="general_sales", energy="medium", notes="Lip main bed (2026-09-24)"),
    dict(id="piano-motivational-148119", file="bgm/piano-motivational-148119.mp3",
         title="Happy Motivational Uplifting Corporate", artist="RomanSenykMusic",
         source="https://pixabay.com/music/corporate-happy-motivational-uplifting-corporate-148119",
         license="Pixabay Content License",
         evidence="subtitle-work/assets/bgm/README.md + page URL above",
         mood="inspiring", energy="medium", notes="Lip alt bed (2026-09-24)"),
    dict(id="guitar-tears-of-joy-839", file="bgm_new/guitar-tears-of-joy-839.mp3",
         title="Tears of Joy", artist="Michael Ramir C.",
         source="https://assets.mixkit.co/music/839/839.mp3",
         license="Mixkit License",
         evidence="subtitle-work/assets/bgm_new/SOURCES.md + https://mixkit.co/license/",
         mood="warm", energy="low", notes="Lip pick 2026-09-30 (กีตาร์เบาๆ)"),
    dict(id="chill-sleepy-cat-135", file="bgm_new/chill-sleepy-cat-135.mp3",
         title="Sleepy Cat", artist="Alejandro Magana",
         source="https://assets.mixkit.co/music/135/135.mp3",
         license="Mixkit License",
         evidence="subtitle-work/assets/bgm_new/SOURCES.md + https://mixkit.co/license/",
         mood="relaxed", energy="low", notes="Lip pick 2026-09-30 (lo-fi/chill)"),
    dict(id="upbeat-feeling-happy-5", file="bgm_new/upbeat-feeling-happy-5.mp3",
         title="Feeling Happy", artist="Ahjay Stelino",
         source="https://assets.mixkit.co/music/5/5.mp3",
         license="Mixkit License",
         evidence="subtitle-work/assets/bgm_new/SOURCES.md + https://mixkit.co/license/",
         mood="fun_upbeat", energy="high", notes="Lip pick 2026-09-30 (upbeat ขายของ)"),
]

SFX = [
    dict(id="click", file="sfx/click.wav", events=["ui_tick"],
         notes="2kHz blip; gen_sfx.py"),
    dict(id="pop", file="sfx/pop.wav", events=["caption_pop"],
         notes="400->900Hz sweep; gen_sfx.py"),
    dict(id="pop_low", file="sfx/pop_low.wav", events=["caption_pop"],
         notes="250->500Hz; batch track-A 2026-09-30"),
    dict(id="riser_08", file="sfx/riser_08.wav", events=["scene_build", "price_reveal"],
         notes="300->2400Hz 0.8s; batch track-A 2026-09-30"),
    dict(id="ching", file="sfx/ching.wav", events=["price_reveal"],
         notes="metallic ting; batch track-A 2026-09-30"),
    dict(id="fast_whoosh", file="sfx/fast_whoosh.wav", events=["transition", "hook_in"],
         notes="bright 0.3s; gen_sfx.py"),
    dict(id="short_whoosh", file="sfx/short_whoosh.wav", events=["transition", "hook_in"],
         notes="swell 0.45s; gen_sfx.py"),
    dict(id="impact_soft", file="sfx/impact_soft.wav", events=["punch", "logo_hit"],
         notes="90Hz thump; gen_sfx.py"),
]

AVOID = ["price", "promo", "product_name", "warranty", "cta"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True, check=True)
    return round(float(r.stdout.strip()), 2)


def main() -> None:
    assets = []
    for b in BGM:
        p = ASSET_ROOT / str(b["file"])
        assets.append({
            "asset_id": b["id"], "kind": "bgm", "logical_path": b["file"],
            "sha256": sha256(p),
            "source_url": b["source"], "origin": "download",
            "license_name": b["license"], "license_evidence": b["evidence"],
            "commercial_use": True, "attribution_required": False,
            "duration_s": duration(p), "mood": b["mood"], "energy": b["energy"],
            "approved": True, "approved_by": "Lip", "approved_at": "2026-09-30",
            "bpm": None, "instrumental": True, "vocal_presence": "none",
            "loop_safe": True, "notes": b["notes"] + "; bpm unmeasured (no meter on VM)",
        })
    for s in SFX:
        p = ASSET_ROOT / str(s["file"])
        assets.append({
            "asset_id": s["id"], "kind": "sfx", "logical_path": s["file"],
            "sha256": sha256(p),
            "source_url": "synthesized on VM (ffmpeg lavfi)",
            "origin": "synth",
            "license_name": "house-synth (team-made, no third-party rights)",
            "license_evidence": "subtitle-work/assets/sfx/SOURCES.md + template-lab/.../editorial-assets/v0.1/gen_sfx.py",
            "commercial_use": True, "attribution_required": False,
            "duration_s": duration(p), "mood": "neutral", "energy": "medium",
            "approved": True, "approved_by": "Lip", "approved_at": "2026-09-30",
            "event_types": s["events"], "min_gap_s": 3.0,
            "avoid_during": AVOID, "notes": s["notes"],
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"registry_version": 1, "assets": assets},
                              ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {OUT} ({len(assets)} assets)")


if __name__ == "__main__":
    main()
