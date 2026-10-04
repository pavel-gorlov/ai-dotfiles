---
id: ai-7xrwf
kind: subtask
status: backlog
created_at: '2026-10-04T11:53:18+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/paths.py
- src/ai_dotfiles/core/dsh_layout.py
- src/ai_dotfiles/core/dsh_targets.py
- tests/unit/test_dsh_paths.py
- tests/unit/test_dsh_targets.py
dependencies: []
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:53:18+00:00'
  status: backlog
---

# Define DSH layout and native target paths

## Goal

Define the concrete project/global DSH layouts and target plans used by later collectors.

Size driver: Five tightly coupled path/planning files, including native discovery edge cases.

## Scope and ownership

Mode: write. Phase 0 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 5, 13; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/paths.py
- src/ai_dotfiles/core/dsh_layout.py
- src/ai_dotfiles/core/dsh_targets.py
- tests/unit/test_dsh_paths.py
- tests/unit/test_dsh_targets.py

## Definition of done

- [ ] DSH_HOME resolution, explicit owned roots and native skill/instruction paths match the approved surface matrix.
- [ ] Project plans distinguish manifest root, nearest Git root, worktree .git files and non-Git cwd; nested manifests expose an explicit native skill-directory binding.
- [ ] Global plans enumerate bounded owned roots and preserve shared user files.
- [ ] New path/target tests cover all listed roots without touching real home; existing Claude/Codex path tests pass.
- [ ] Public functions remain typed and core failures use the existing error hierarchy.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
