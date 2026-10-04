---
id: ai-efsr3
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_install.py
- src/ai_dotfiles/core/fs_copy.py
- src/ai_dotfiles/core/symlinks.py
- tests/integration/test_dsh_target.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
---

# Install DSH elements with copy link and provenance ownership

## Goal

Install rendered catalog elements through existing safe link/copy primitives with precise ownership and drift metadata.

Size driver: One target installer, reused filesystem primitives and install ownership tests.

## Scope and ownership

Mode: write. Phase 1 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 6, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_install.py
- src/ai_dotfiles/core/fs_copy.py
- src/ai_dotfiles/core/symlinks.py
- tests/integration/test_dsh_target.py

## Definition of done

- [ ] Valid skill directories install natively in both scopes with safe symlink/copy behaviour and no Codex length transformation.
- [ ] Rendered agents/rules/bridge resources carry source and generator provenance and foreign paths are preserved on collision.
- [ ] Resources required for DSH exist even when Claude is not an installed target.
- [ ] Install operations expose contributions/resources for later reconcile and prune; global writes stay under explicit roots or managed blocks.
- [ ] Integration tests cover links, copies, user collisions, source/generator drift and idempotent installation.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
