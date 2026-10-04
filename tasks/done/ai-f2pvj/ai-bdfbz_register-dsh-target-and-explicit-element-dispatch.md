---
id: ai-bdfbz
kind: subtask
status: done
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
- at: '2026-10-04T12:50:15+00:00'
  status: to_do
- at: '2026-10-04T12:50:15+00:00'
  status: wip
- at: '2026-10-04T13:06:27+00:00'
  status: done
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

- [x] Target/RENDER_POLICY includes DSH with the approved capabilities and both scopes.
- [x] Element dispatch has a dedicated DSH branch; non-Claude paths never fall through to Codex.
- [x] Default target, empty target lists and unknown-target handling keep their existing behaviour.
- [x] Existing target/element tests include DSH-only and mixed-target cases and pass.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** Layout prerequisite ai-7xrwf is done and committed
as 190b85d. This Phase 0 row owns targets.py/elements.py and their two
existing unit suites; preserve default, empty and unknown manifest targets.
Use the concrete DSH paths from the prior row; no active file conflicts.

**to_do → wip.** Selected by tm next --epic ai-47xpm; worker receives
the entire generated context and approved parent contract. Only four
declared files are writable. Test/type/lint/format gates precede acceptance.

**wip → done.** Actual four-file diff inspected. Target.DSH has explicit
policy/dispatch; resolve_target_paths accepts Path or DshLayout for DSH.
Agent/literal-rule pairs are aggregate config contributions, never copies.
Source paths are checked before Codex classification; glob+always_on stays
unsupported for DSH while existing Codex behavior is preserved. With the
isolated Poetry environment: pytest tests/unit/test_targets.py
tests/unit/test_elements.py -q: 106 passed; pytest tests/unit/test_dsh_paths.py
tests/unit/test_dsh_targets.py tests/unit/test_codex_targets.py
tests/unit/test_rule_classify.py tests/unit/test_paths.py tests/unit/test_manifest.py
tests/e2e/test_codex_install.py tests/e2e/test_codex_global.py -q: 164 passed.
mypy src/ (74 files), Ruff/Black on the four owned files and diff --check
passed, all exit 0. Native rendering/activation remains a later gate.
