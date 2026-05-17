---
id: ai-12
kind: subtask
status: to_do
created_at: '2026-05-17T10:57:40+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md
- README.md
dependencies:
- ai-11
executor_agent: claude
---

# Codex target: Phase 2 docs

## Goal

Document Codex rule support so users and Claude (via the builtin skill)
get correct advice for Phase 2 behaviour.

## Context files

- `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md` —
  document rule rendering for the Codex target: the three rule classes,
  the `paths:` frontmatter field, `AGENTS.md` assembly, and the
  `rule-<name>` Codex-only skill. Required by the project `CLAUDE.md`
  builtin-skill-sync rule.
- `README.md` — document the `paths:` rule field and Codex rule support
  at user level; remove the Phase 1 "rules not yet rendered" limitation.

## Definition of done

- [ ] `builtin_ai_dotfiles_skill.md` documents the three rule classes, `paths:`, `AGENTS.md` assembly, and `rule-<name>` skills.
- [ ] `README.md` covers the `paths:` field and Codex rule support; the stale Phase 1 limitation note is removed.
- [ ] No doc claims behaviour beyond Phase 2 (`config.toml` / MCP are Phase 3 — do not document as available).

## Notes

- Verify every claim against the shipped ai-9..ai-11 code.
- Depends on ai-11.
