---
id: ai-7xrwf
kind: subtask
status: done
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
mode: write
phase: 1
status_history:
- at: '2026-10-04T11:53:18+00:00'
  status: backlog
- at: '2026-10-04T12:27:18+00:00'
  status: to_do
- at: '2026-10-04T12:27:39+00:00'
  status: wip
- at: '2026-10-04T12:45:17+00:00'
  status: done
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

- [x] DSH_HOME resolution, explicit owned roots and native skill/instruction paths match the approved surface matrix.
- [x] Project plans distinguish manifest root, nearest Git root, worktree .git files and non-Git cwd; nested manifests expose an explicit native skill-directory binding.
- [x] Global plans enumerate bounded owned roots and preserve shared user files.
- [x] New path/target tests cover all listed roots without touching real home; existing Claude/Codex path tests pass.
- [x] Public functions remain typed and core failures use the existing error hierarchy.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** First eligible Phase 0 row; no dependencies or active
file conflicts. Owner scope is paths.py, dsh_layout.py, dsh_targets.py and
their two new unit suites. Required focused path/planning tests plus type,
lint and format gates must pass before acceptance.

**to_do → wip.** tm next --epic ai-47xpm selected this exact child.
Worker receives the full generated context and approved parent contract;
only the five declared paths are writable. No tracker edits or commits.

**wip → done.** Reviewed the actual five-file diff and all 38 new tests.
Focused command after the isolated Poetry prefix: pytest
tests/unit/test_dsh_paths.py tests/unit/test_dsh_targets.py
tests/unit/test_paths.py tests/unit/test_codex_targets.py
tests/unit/test_codex_global.py tests/unit/test_targets.py
tests/unit/test_elements.py — 133 passed in 0.17s, exit 0, no skips.
mypy src/ — 74 source files clean, exit 0; owned-path Ruff and Black
checks passed (five files), exit 0; git diff --check exit 0.
Native package/field constants were checked against pinned source and
Node lexical path probes. tm acceptance: 5/5; native activation belongs
to later required runtime gates. The git executor commits this transaction.
