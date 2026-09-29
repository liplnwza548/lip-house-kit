# AGENTS.md — lip-house-kit

Working language: Thai-first (Lip's house). Reports short; plans and
reviews in clear full sentences. Meters and file paths are evidence —
never claim done without them.

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues (`gh` CLI). See
`docs/agents/issue-tracker.md`.

### Domain docs

Single-context: root `CONTEXT.md` + `docs/adr/`. Read them before
exploring. See `docs/agents/domain.md`.

## House rules (mirror Lip's locked principles)

1. Same source VO rendered into any number of clips must measure the
   same (meters, not ears alone).
2. Stuck anywhere = stop loudly. Never guess onward, never burn garbage.
3. Locked wording (Lip's ear) overrides every transcript, always.
4. Loanwords in a script: check tokenization before burning; register
   unknowns in `glossary/loanword_dict.json` with protect:true.
5. Canonical VO only (`tools/vo_ingest.py` + manifest) — never
   re-normalize per batch.
6. No keys, no client work, no media binaries in this repo (.gitignore
   enforces it).

## Workflow

grill-with-docs → to-spec → to-tickets → implement → code-review.
Factory order: scout → edit → review → subtitle → audio → qa.
Each factory reads a work order (schemas/) and refuses bad input loudly.
