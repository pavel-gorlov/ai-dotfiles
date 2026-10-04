---
id: ai-b8jes
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/commands/domain.py
- tests/e2e/test_dsh_domain.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 4
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
---

# Wire DSH domain add and remove lifecycle

## Goal

Route domain mutations through selected-target collectors in project and global scope.

Size driver: One existing domain wrapper and multi-domain/scoped CLI regression cases.

## Scope and ownership

Mode: write. Phase 3 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 4, 5, 9, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/commands/domain.py
- tests/e2e/test_dsh_domain.py

## Definition of done

- [ ] Domain add/remove respects selected DSH targets and both catalog scopes instead of assuming Claude-only installation.
- [ ] Native fragments, agent/MCP rows, hooks and copied resources enter/retire through core collectors with source ownership.
- [ ] Adding a second domain retains the first; removing one preserves other domains and user contributions.
- [ ] Existing dependency/runtime bin machinery is reused and update/vendor/pull stay catalog-only.
- [ ] New CLI tests exercise DSH-only/mixed-target domain mutations, dependency order, collisions and both scopes.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
