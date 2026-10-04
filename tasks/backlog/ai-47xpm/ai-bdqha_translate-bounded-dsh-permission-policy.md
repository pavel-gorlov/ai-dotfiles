---
id: ai-bdqha
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_permissions.py
- tests/unit/test_dsh_permissions.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
---

# Translate bounded DSH permission policy

## Goal

Translate only exact known whole-tool deny/ask entries into policy data for the native bridge.

Size driver: One bounded translator plus cases proving that unsupported expressions never broaden access.

## Scope and ownership

Mode: write. Phase 1 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 6, 8; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_permissions.py
- tests/unit/test_dsh_permissions.py

## Definition of done

- [ ] Known tool names map explicitly; deny and ask policy data retain origin and diagnostic provenance.
- [ ] Arguments, compound Bash expressions, unknown names and allow entries are reported rather than approximated.
- [ ] No entry enables a broader permission preset or full-access fallback.
- [ ] Translator tests cover exact mappings, unsupported patterns, repeated origins and preservation of source policy.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
