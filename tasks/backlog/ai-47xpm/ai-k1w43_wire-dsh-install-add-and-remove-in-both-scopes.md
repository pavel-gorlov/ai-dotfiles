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
- src/ai_dotfiles/core/dsh_migrate.py
- tests/e2e/test_dsh_install.py
dependencies:
- ai-7xrwf
- ai-nzmc8
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

Size driver: Three command wrappers, the narrow registered-local producer selection and one project/global CLI suite share one catalog lifecycle concern.

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
- src/ai_dotfiles/core/dsh_migrate.py
- tests/e2e/test_dsh_install.py

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

## Execution notes

**Concrete lifecycle probe → bounded producer selection.** ai-m4s7p's full
opted-in reconciliation correctly discovers new local sources, but catalog-only
install/add/remove must not silently adopt them. Selection must happen before
local rendering/collision and retain the complete observed original-source set
for guards: post-filtering inputs either fails source-set proof or leaves an
unregistered guarded projection active. This owner adds the narrow selection in
dsh_migrate.py, using fresh registered originals, no stored snapshot or user flag.
All project/global CLI cases consolidate in test_dsh_install.py, keeping exactly
five owned files and all six acceptance criteria. Existing migrate/reconcile
defaults remain full discovery. Fresh whole-cut critic must pass before dispatch.

**Shared refresh probe → target mutation ordering.** Coordinator disposable
probe exits0: after catalog shared rule body changes, Codex-first block mutation
causes DSH historical custody refusal; DSH-first refresh followed by Codex gives
clean check. The command owner must consume the union and preflight/current
originals in the correct order, including Claude settings/ledger rebuilds; prove
mixed-target repeated install and changed catalog rule refresh remain clean.
No historical guard may be relaxed to compensate for earlier target writes.
