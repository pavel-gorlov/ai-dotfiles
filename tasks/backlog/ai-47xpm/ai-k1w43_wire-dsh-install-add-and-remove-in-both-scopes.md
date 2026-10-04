---
id: ai-k1w43
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/commands/install.py
- src/ai_dotfiles/commands/add.py
- src/ai_dotfiles/commands/remove.py
- tests/e2e/test_dsh_install.py
- tests/e2e/test_dsh_global.py
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

# Wire DSH install add and remove in both scopes

## Goal

Connect existing catalog lifecycle commands and their applicable flags to DSH core services in project/global scope.

Size driver: Three existing command wrappers and two CLI suites; all catalog mutation dispatch has one owner.

## Scope and ownership

Mode: write. Phase 3 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 5, 10, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/commands/install.py
- src/ai_dotfiles/commands/add.py
- src/ai_dotfiles/commands/remove.py
- tests/e2e/test_dsh_install.py
- tests/e2e/test_dsh_global.py

## Definition of done

- [ ] DSH-only and Claude+Codex+DSH install/add/remove work in project and -g scope with existing applicable flags.
- [ ] Command wrappers delegate logic to core and format errors through ui; no new business logic is added to commands.
- [ ] Catalog-only install does not silently migrate local elements; local provenance remains protected on remove/prune.
- [ ] Codex and DSH shared project blocks use the coordinator before both existing Codex and new DSH destructive paths, including empty manifests.
- [ ] User content, other domains and global shared configuration survive removal/prune and collisions.
- [ ] CLI tests cover --prune, copy/link mode, target combinations and existing default/unknown-target regressions.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
