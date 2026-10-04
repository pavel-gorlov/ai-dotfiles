---
id: ai-4m4hj
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_hooks.py
- tests/unit/test_dsh_hooks.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 3
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
---

# Translate supported DSH command hooks and resource bindings

## Goal

Produce one combined native hooks configuration and origin-bound resource plan for the seven supported command events.

Size driver: One hooks collector with matcher, protocol and path-binding tests.

## Scope and ownership

Mode: write. Phase 2 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 6, 9, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_hooks.py
- tests/unit/test_dsh_hooks.py

## Definition of done

- [ ] The seven matrix events combine across domains/scopes into one hooks.json using the native compatibility plugin.
- [ ] Known exact tool matchers translate; event, matcher, handler/async/once and output compatibility gaps are reported before native parsing ignores them.
- [ ] Handlers/support resources bind to their source origin and the launcher project without depending on a Claude install.
- [ ] Required unsupported handler semantics are MANUAL; supported exit-2/context/Stop behaviour has test coverage.
- [ ] Tests cover multiple domains, global/project bindings and every listed unsupported hook field.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
