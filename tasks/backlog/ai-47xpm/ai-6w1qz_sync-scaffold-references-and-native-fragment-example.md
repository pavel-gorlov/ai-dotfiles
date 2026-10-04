---
id: ai-6w1qz
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:44+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/scaffold/templates/global_readme.md
- src/ai_dotfiles/scaffold/templates/root_readme.md
- src/ai_dotfiles/scaffold/templates/example_dsh_fragment.json
dependencies:
- ai-7xrwf
executor_agent: claude
size: S
mode: write
phase: 5
status_history:
- at: '2026-10-04T11:57:44+00:00'
  status: backlog
---

# Sync scaffold references and native fragment example

## Goal

Keep shipped scaffold references aligned and provide a documentation example of the native fragment contract.

Size driver: Two reference templates and one JSON-data example; no onboarding behaviour changes.

## Scope and ownership

Mode: write. Phase 4 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 4, 14; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/scaffold/templates/global_readme.md
- src/ai_dotfiles/scaffold/templates/root_readme.md
- src/ai_dotfiles/scaffold/templates/example_dsh_fragment.json

## Definition of done

- [ ] Shipped reference templates describe applicable DSH target/lifecycle and point to managed launcher guidance.
- [ ] The example is a valid JSON patch array using the pinned native contract without executable expressions or secrets.
- [ ] No default target, init flag or automatic profile/runtime installation is added.
- [ ] Template examples are checked against the implemented collector and documentation.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
