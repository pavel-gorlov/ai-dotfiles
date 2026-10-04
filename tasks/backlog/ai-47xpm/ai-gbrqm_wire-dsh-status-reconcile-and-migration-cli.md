---
id: ai-gbrqm
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/commands/status.py
- src/ai_dotfiles/commands/reconcile.py
- src/ai_dotfiles/commands/migrate.py
- src/ai_dotfiles/core/completions.py
- tests/e2e/test_dsh_migrate.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
---

# Wire DSH status reconcile and migration CLI

## Goal

Expose DSH drift/reconcile and project migration with consistent command output and completion.

Size driver: Three thin wrappers, completion and the associated CLI acceptance suite.

## Scope and ownership

Mode: write. Phase 3 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 5, 6, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/commands/status.py
- src/ai_dotfiles/commands/reconcile.py
- src/ai_dotfiles/commands/migrate.py
- src/ai_dotfiles/core/completions.py
- tests/e2e/test_dsh_migrate.py

## Definition of done

- [ ] status/reconcile and applicable -g/--check behaviour include DSH without losing existing Codex local-only behaviour.
- [ ] migrate --to dsh and --dry-run are available in Choice/help/completion while preserving the existing default and project-only migration scope.
- [ ] Errors and unsupported fields identify origin/reason through ui and core exception handling.
- [ ] CLI tests verify drift exit status, check/dry-run zero-writes, migration classification and default/unknown-target regression.
- [ ] Applicable existing command tests pass and no new global migration flag is introduced.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
