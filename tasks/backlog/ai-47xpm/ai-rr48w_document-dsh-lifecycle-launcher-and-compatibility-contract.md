---
id: ai-rr48w
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- README.md
- src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md
- docs/dsh-target.md
dependencies:
- ai-7xrwf
executor_agent: claude
size: S
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
---

# Document DSH lifecycle launcher and compatibility contract

## Goal

Update the public CLI reference and document the complete approved DSH workflow and matrix boundaries.

Size driver: Three documentation files with already-decided CLI and native contracts.

## Scope and ownership

Mode: write. Phase 4 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 3, 4, 6, 9, 14, 16; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- README.md
- src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md
- docs/dsh-target.md

## Definition of done

- [ ] README and builtin ai-dotfiles skill agree with new command/flags/targets/vendor and domain workflows in this PR.
- [ ] The guide documents project/global roots, DSH_HOME, managed startup/restart/project binding, native JSON patch syntax and whole-config replacement.
- [ ] Native UI override behaviour, current-model alias inheritance, collisions, provenance/reconcile and every matrix limitation are explicit.
- [ ] Examples match actual help and finite native contract; no parity or security claim exceeds the pinned APIs.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
