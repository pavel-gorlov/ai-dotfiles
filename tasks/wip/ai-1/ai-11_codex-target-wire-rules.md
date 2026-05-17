---
id: ai-11
kind: subtask
status: wip
created_at: '2026-05-17T10:57:40+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/core/codex_install.py
- src/ai_dotfiles/core/codex_targets.py
- src/ai_dotfiles/commands/install.py
- src/ai_dotfiles/commands/remove.py
dependencies:
- ai-10
executor_agent: claude
---

# Codex target: wire rules

## Goal

Wire rule rendering into the Codex target: `ALWAYS_ON` / `PATH_SCOPED`
rules drive `AGENTS.md` assembly, `DESCRIPTION_ONLY` rules render as
Codex-only `rule-<name>` skills — applied and reverted by the commands.

## Context files

- `src/ai_dotfiles/core/codex_install.py` — extend the apply layer:
  invoke `agents_md` assembly (ai-10) for always-on / path-scoped rules;
  render each `DESCRIPTION_ONLY` rule as a Codex-only skill named
  `rule-<name>` (ADR ai-1-2 — `render_skill_md` shape, never installed
  for the Claude target); `remove` strips owned `AGENTS.md` blocks and
  the synthetic skills.
- `src/ai_dotfiles/core/codex_targets.py` — extend `iter_codex_pairs()`
  so `rules/` is no longer a skipped subdir for the Codex target.
- `src/ai_dotfiles/commands/install.py`, `remove.py` — route rules
  through the new apply paths for the Codex target. `status` may need a
  rules line; keep it minimal.

## Definition of done

- [ ] An always-on rule lands in the root `AGENTS.md`; a path-scoped rule lands in `<dir>/AGENTS.md`.
- [ ] A description-only rule renders as a Codex-only `rule-<name>` skill, never installed for the Claude target.
- [ ] `remove` strips owned `AGENTS.md` blocks and synthetic skills; user `AGENTS.md` text untouched.
- [ ] `rules/` is no longer skipped for the Codex target; the skip message is gone for rules.
- [ ] Integration + e2e tests cover the three rule classes through `install`/`remove`.
- [ ] `pytest`, `mypy --strict`, `ruff`, `black` green.

## Notes

- Depends on ai-9 (`rule_classify`) and ai-10 (`agents_md`).
- `commands/` stays a thin wrapper — logic in `core/`.
- Tests are folded into this subtask (the epic Phase 2 plan).
