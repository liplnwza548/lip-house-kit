# CONTEXT.md — lip-house-kit (single-context)

## What this repo is

House kit: subtitle + audio factory presets, glossary, schemas, shared
tools, and six factory pipelines. Public mirror — no keys, no client
work, no media binaries (see .gitignore).

## Vocabulary (use these terms, not synonyms)

- **Factory**: one stage with a work order in and an artifact out
  (scout, edit, review, subtitle, audio, qa).
- **Work order**: the JSON file a factory reads (schemas/*.schema.json).
- **Canonical VO**: the single normalized voiceover file every clip pulls
  (tools/vo_ingest.py + manifest.json) — never re-normalize per batch.
- **Gate**: a check that refuses loudly instead of shipping bad output.
- **Lip-locked**: wording/timing Lip personally approved; overrides every
  transcript.
- **Charter**: the standing role prompt an agent works under
  (roles/agy-reviewer-charter.md) — prep only, never the decider.

## Fixed numbers (mirrors presets/house.yaml)

Master -15±1 LUFS · VO stem ≈-17 · BGM -20dB ducked · SFX bus 0.2 ·
Viral Pop Prompt-Bold 104 at (540,1580) · cue floor 0.5s / 8 syl.

## Workflow (Matt Pocock skills)

grill-with-docs → to-spec → to-tickets → implement → code-review.
Issues live on GitHub (docs/agents/issue-tracker.md).
