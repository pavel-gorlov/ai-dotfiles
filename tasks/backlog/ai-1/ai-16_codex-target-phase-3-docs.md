---
id: ai-16
kind: subtask
status: backlog
created_at: '2026-05-17T10:57:41+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md
- README.md
dependencies:
- ai-15
executor_agent: claude
---

# Codex target: Phase 3 docs

## Goal

Document Codex `config.toml` + MCP support so users and Claude (via the
builtin skill) get correct advice for Phase 3 behaviour.

## Context files

- `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md` —
  document `settings.fragment.json` → `.codex/config.toml` translation
  (which keys map, hooks skipped) and `mcp.fragment.json` →
  `[mcp_servers]`. Required by the project `CLAUDE.md` builtin-skill-sync
  rule.
- `README.md` — document Codex `config.toml` + MCP support at user
  level; remove the Phase 1 "config.toml / MCP not yet" limitation note.

## Definition of done

- [ ] `builtin_ai_dotfiles_skill.md` documents the settings→config.toml mapping (incl. the hooks skip) and the MCP→`[mcp_servers]` mapping.
- [ ] `README.md` covers Codex `config.toml` + MCP support; the stale Phase 1 limitation note is removed.
- [ ] No doc claims behaviour beyond Phase 3 (global Codex install remains out of scope per the epic).

## Notes

- Verify every claim against the shipped ai-14..ai-15 code.
- Depends on ai-15.
