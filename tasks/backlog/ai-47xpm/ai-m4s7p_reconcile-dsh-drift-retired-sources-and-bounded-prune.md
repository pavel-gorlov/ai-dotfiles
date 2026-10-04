---
id: ai-m4s7p
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_reconcile.py
- src/ai_dotfiles/core/gitignore.py
- tests/integration/test_dsh_reconcile.py
- tests/integration/test_dsh_prune.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
---

# Reconcile DSH drift retired sources and bounded prune

## Goal

Regenerate stale owned artefacts and retire deleted contributions while preserving mixed-target and user ownership.

Size driver: One reconciliation concern with shared-block, registry and bounded-prune edge cases.

## Scope and ownership

Mode: write. Phase 3 of approved epic ai-47xpm.
Implement Pre-decided decisions 2, 10, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_reconcile.py
- src/ai_dotfiles/core/gitignore.py
- tests/integration/test_dsh_reconcile.py
- tests/integration/test_dsh_prune.py

## Definition of done

- [ ] Missing/source/generator/resource/contribution drift is reported consistently and regenerated in write mode.
- [ ] Registry-versus-discovery retirement removes deleted local sources' owned outputs without touching user paths.
- [ ] Check mode changes zero bytes and returns failure on drift; empty selected manifests clean up owned contributions.
- [ ] Project prune consults the shared catalog/local union; global prune visits explicit owned roots/blocks and never walks home.
- [ ] Managed link paths integrate with gitignore policy without ignoring an entire user AGENTS.md.
- [ ] New tests cover check zero-writes, local preservation, single-target removal, bounded global prune and removed-source retirement.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
