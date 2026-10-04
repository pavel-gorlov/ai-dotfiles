---
id: ai-bdfbz
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/targets.py
- src/ai_dotfiles/core/elements.py
- tests/unit/test_targets.py
- tests/unit/test_elements.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
---

# Register DSH target and explicit element dispatch

## Goal

Make DSH an explicit target in existing target policy and element path dispatch.

Size driver: Two shared modules and their regression suites; default and unknown-target behaviour must survive.

## Scope and ownership

Mode: write. Phase 0 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 5, 6; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/targets.py
- src/ai_dotfiles/core/elements.py
- tests/unit/test_targets.py
- tests/unit/test_elements.py

## Definition of done

- [ ] Target/RENDER_POLICY includes DSH with the approved capabilities and both scopes.
- [ ] Element dispatch has a dedicated DSH branch; non-Claude paths never fall through to Codex.
- [ ] Default target, empty target lists and unknown-target handling keep their existing behaviour.
- [ ] Existing target/element tests include DSH-only and mixed-target cases and pass.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
