---
id: ai-7
kind: subtask
status: done
created_at: '2026-05-17T07:09:43+00:00'
parent: ai-1
context_files:
- src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md
- README.md
- CLAUDE.md
dependencies:
- ai-5
executor_agent: claude
---

# Codex target: Phase 1 docs

## Goal

Document the Codex target so users (and Claude operating via the
builtin skill) get correct advice — keep docs in sync with the shipped
Phase 1 behaviour.

## Context files

- `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md` —
  the shipped `ai-dotfiles` skill reference. Add the `targets` manifest
  field, the Codex target behaviour (skills → `.agents/skills/`, agents
  → `.codex/agents/*.toml`), and the regenerate-on-change note. Required
  by the project `CLAUDE.md` rule for every user-visible change.
- `README.md` — document `targets` and Codex support at user level.
- `CLAUDE.md` — add the maintenance note (ADR ai-1-1): when a catalog
  agent's source `.md` changes, regenerate its Codex `.toml`
  (`ai-dotfiles install`); `status` flags drift.

## Definition of done

- [x] `builtin_ai_dotfiles_skill.md` documents `targets` and Codex render behaviour, consistent with shipped Phase 1.
- [x] `README.md` covers the `targets` field and Codex support.
- [x] `CLAUDE.md` carries the regenerate-on-change maintenance note.
- [x] No doc claims behaviour beyond Phase 1 (rules / config.toml / MCP / global are Phases 2–3 — do not document as available).

## Notes

- Phase 1 only: skills + agents, project-scoped. Do not document rules,
  `config.toml`, MCP, or global Codex install — those are later phases.
- Depends on ai-5 — docs must describe the actually-shipped behaviour.
