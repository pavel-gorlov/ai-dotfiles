---
id: ai-bdqha
kind: subtask
status: done
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
- at: '2026-10-04T14:01:57+00:00'
  status: to_do
- at: '2026-10-04T14:02:16+00:00'
  status: wip
- at: '2026-10-04T14:15:30+00:00'
  status: done
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

- [x] Known tool names map explicitly; deny and ask policy data retain origin and diagnostic provenance.
- [x] Arguments, compound Bash expressions, unknown names and allow entries are reported rather than approximated.
- [x] No entry enables a broader permission preset or full-access fallback.
- [x] Translator tests cover exact mappings, unsupported patterns, repeated origins and preservation of source policy.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** Renderer prerequisite is accepted and committed
as 1baa6da after 411 tests/mypy76/Ruff/Black/commit gates. Reuse
dsh_render.native_tool_names and DshDiagnostic; Read maps read+read_image.
No shell parser, prefix widening or new permission preset belongs here.

**to_do → wip.** Selected by tm next --epic ai-47xpm as the next
Phase 1 row. Complete context and approved parent contract go to one
writer owning exactly the translator and its unit suite. Bridge enforcement
and native approval behavior remain ai-8n95c responsibility.

**wip → done.** Coordinator inspected both complete source/test files and
confirmed focused pytest: 385 passed (146 permission cases), exit 0.
Worker evidence: mypy src/ 77 files, owned Ruff/Black and diff whitespace
checks pass. translate_permissions takes each original source plus
DshProvenance; merge_permission_policies retains repeats and origins.
bridge_data schemaVersion=1/generator=1 includes deny/ask/requiredTools,
blocked, contributions and diagnostics/raw values. Names deduplicate only
in sorted views. Unsupported deny/ask, malformed/unknown permission fields
block activation; allow-only gaps grant nothing and remain nonblocking.
No native preset, shell parser or enforcement is introduced. The next
bridge owner must reject blocked/unknown-schema/malformed payloads and
source JSON parse failures, audit read_image with Read, retain the final
deny guard and preserve downstream ask decisions. Native smoke is pending.
Acceptance, move and required commit gates belong to this code transaction.
