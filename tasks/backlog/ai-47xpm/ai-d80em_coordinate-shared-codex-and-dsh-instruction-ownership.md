---
id: ai-d80em
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/shared_instructions.py
- src/ai_dotfiles/core/agents_md.py
- tests/unit/test_shared_instructions.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
---

# Coordinate shared Codex and DSH instruction ownership

## Goal

Expose a narrow desired-block union for shared project instructions before any destructive lifecycle operation.

Size driver: One ownership coordinator, managed-block primitives and mixed-target tests.

## Scope and ownership

Mode: write. Phase 0 of approved epic ai-47xpm.
Implement Pre-decided decisions 2, 7, 10, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/shared_instructions.py
- src/ai_dotfiles/core/agents_md.py
- tests/unit/test_shared_instructions.py

## Definition of done

- [ ] Desired project blocks union enabled Codex/DSH catalog contributions and both local provenance registries.
- [ ] Managed marker/source hashes stay compatible and user-authored Markdown survives updates and removal.
- [ ] Existing Codex rule classification is preserved; DSH-only description rules are excluded from shared activation and routed through the DSH literal bridge.
- [ ] The coordinator exposes the wanted/protected sets needed by install/remove/prune and empty-manifest cleanup.
- [ ] Mixed-target tests cover single-target removal, local contributors, identical source blocks and source drift.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
