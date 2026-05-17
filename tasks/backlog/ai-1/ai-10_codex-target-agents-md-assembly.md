---
id: ai-10
kind: subtask
status: backlog
created_at: '2026-05-17T10:57:40+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/core/agents_md.py
- src/ai_dotfiles/core/settings_merge.py
- src/ai_dotfiles/core/rule_classify.py
dependencies:
- ai-9
executor_agent: claude
---

# Codex target: AGENTS.md assembly

## Goal

Assemble project `AGENTS.md` files (root and nested) from classified
rules, with marker-delimited managed blocks that `remove` can strip
without touching user-authored text.

## Context files

- `src/ai_dotfiles/core/agents_md.py` — **new.** Given a set of rules
  and their `RuleClass` (from ai-9): write/update a managed block in the
  project-root `AGENTS.md` for each `ALWAYS_ON` rule, and in
  `<dir>/AGENTS.md` for each `PATH_SCOPED` rule's directories. Blocks are
  delimited by markers (e.g. `<!-- ai-dotfiles:rule:<name> -->` …
  `<!-- /ai-dotfiles:rule:<name> -->`). Provide a `strip_owned` analogue
  that removes only ai-dotfiles blocks, preserving user content.
- `src/ai_dotfiles/core/settings_merge.py` — read-only reference for the
  ownership/`strip_owned` pattern already used for `settings.json`.
- `src/ai_dotfiles/core/rule_classify.py` — consumed (from ai-9).

## Definition of done

- [ ] `agents_md.py` writes an `ALWAYS_ON` rule as a managed block in the root `AGENTS.md`.
- [ ] A `PATH_SCOPED` rule is written as a managed block in each target `<dir>/AGENTS.md`.
- [ ] Managed blocks are marker-delimited; the strip function removes only ai-dotfiles blocks and preserves user text.
- [ ] Re-running assembly is idempotent (no duplicate blocks, no drift).
- [ ] Unit tests cover write, idempotent re-write, strip, and user-text preservation.
- [ ] `pytest`, `mypy --strict`, `ruff`, `black` green.

## Notes

- `DESCRIPTION_ONLY` rules are NOT handled here — they become Codex-only
  skills in ai-11.
- Assembly logic only — no command wiring (ai-11).
- Depends on ai-9 (`rule_classify`).
