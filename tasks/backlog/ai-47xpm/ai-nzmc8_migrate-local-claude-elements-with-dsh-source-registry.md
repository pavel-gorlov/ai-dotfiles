---
id: ai-nzmc8
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_migrate.py
- src/ai_dotfiles/core/dsh_local_registry.py
- src/ai_dotfiles/core/local_discovery.py
- tests/integration/test_dsh_migrate.py
- tests/integration/test_local_discovery.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
---

# Migrate local Claude elements with DSH source registry

## Goal

Discover and classify project-local sources and retain enough provenance for later retirement/reconciliation.

Size driver: Migration, local registry and discovery boundaries with copy-mode regressions.

## Scope and ownership

Mode: write. Phase 3 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 6, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_migrate.py
- src/ai_dotfiles/core/dsh_local_registry.py
- src/ai_dotfiles/core/local_discovery.py
- tests/integration/test_dsh_migrate.py
- tests/integration/test_local_discovery.py

## Definition of done

- [ ] Local skills/agents/rules/commands/settings/settings.local/.mcp.json/hooks classify as MECHANICAL/REFACTOR/MANUAL through the approved matrix.
- [ ] Catalog domain symlinks and copy-owned paths are excluded from local discovery.
- [ ] Registry records outputs, contributions and resources by source with source/generator provenance.
- [ ] Dry-run writes no bytes, including activation/profile snapshots, and reports origin/field/reason for gaps.
- [ ] Discovery and migration tests cover copy mode, foreign files, unsupported restrictions and project-only scope.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
