---
id: ai-9
kind: subtask
status: wip
created_at: '2026-05-17T10:57:40+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/core/rule_classify.py
- src/ai_dotfiles/core/targets.py
- src/ai_dotfiles/core/frontmatter.py
executor_agent: claude
---

# Codex target: rule classification

## Goal

Add an optional `paths:` frontmatter field to rules and a classifier
that sorts every rule into one of three Codex activation modes:
always-on, path-scoped, description-only.

## Context files

- `src/ai_dotfiles/core/rule_classify.py` — **new.** `classify_rule(md_path)
  -> RuleClass` where `RuleClass` is one of `ALWAYS_ON` / `PATH_SCOPED`
  / `DESCRIPTION_ONLY`. Rule: a `paths:` field present ⇒ `PATH_SCOPED`;
  an explicit always-on marker (decide the convention — e.g. a frontmatter
  flag or the existing "Always-loaded" signal) ⇒ `ALWAYS_ON`; otherwise
  `DESCRIPTION_ONLY`.
- `src/ai_dotfiles/core/targets.py` — the `RULE` render policy for
  `Target.CODEX` is currently `RenderMode.SKIP` (Phase 1). Replace it so
  rule handling dispatches on `RuleClass`.
- `src/ai_dotfiles/core/frontmatter.py` — consumed (the `paths:` field is
  read via `parse_frontmatter`), read-only.

## Definition of done

- [ ] Rule frontmatter supports an optional `paths:` field (list of directory globs).
- [ ] `classify_rule` returns `ALWAYS_ON` / `PATH_SCOPED` / `DESCRIPTION_ONLY` deterministically.
- [ ] `targets.py` rule policy for `Target.CODEX` reflects the three classes (no longer a flat `SKIP`).
- [ ] Unit tests cover each class incl. edge cases (empty `paths:`, both signals present).
- [ ] `pytest`, `mypy --strict`, `ruff`, `black` green.

## Notes

- Design rationale in epic [ai-1](../ai-1_openai-codex-cli-support-target-adapters.md)
  Phase 2 + ADR ai-1-2. Do not restate.
- Classification only — no `AGENTS.md` writing (ai-10), no command
  wiring (ai-11).
