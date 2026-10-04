---
id: ai-86vb3
kind: subtask
status: done
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_render.py
- tests/unit/test_dsh_render.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 2
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
- at: '2026-10-04T13:31:07+00:00'
  status: to_do
- at: '2026-10-04T13:31:25+00:00'
  status: wip
- at: '2026-10-04T13:59:02+00:00'
  status: done
---

# Render DSH skills rules and callable agent payloads

## Goal

Render faithful native elements and agent payloads from catalog/local source without lossy activation.

Size driver: One renderer and its matrix tests, including rule classification and agent metadata.

## Scope and ownership

Mode: write. Phase 1 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 6, 7, 9, 16; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_render.py
- tests/unit/test_dsh_render.py

## Definition of done

- [x] Native skill names, descriptions and invocation fields are validated without Codex description truncation.
- [x] Shared always-on rule payloads and DSH-only literal description-rule sections preserve source bodies; path-scoped activation gaps are reported.
- [x] Each supported agent emits one uniquely named native subagent-tool row with literal persona, description, known child filters and retained source provenance.
- [x] Unknown/unrepresentable tool restrictions make the affected agent MANUAL instead of unrestricted.
- [x] Omitted/inherit and Claude-only aliases use the current parent session route; aliases emit MODEL_UNMAPPED; native routes stay explicit.
- [x] Renderer tests cover braces/whitespace, invalid input, diagnostics by origin and no invented provider/model identifiers.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** Phase 0's three commits and gate are verified:
190b85d, 2c8c2bc, 79ae642; full pytest 1249/1249, mypy75/Ruff/Black clean.
This row owns only dsh_render.py and its new unit suite. Runtime bridge,
permission translator, installer and configuration consumers follow later.

**to_do → wip.** Selected by tm next --epic ai-47xpm as the first
Phase 1 writer. Worker receives complete generated context, approved epic
and native source contracts. Literal source content, known exact tool filters,
MANUAL gaps and current-parent model inheritance are mandatory.

**wip → done.** Actual new source/test files inspected, all six renderer
criteria demonstrated. APIs validate_skill/render_rule/render_agent produce
READY/DEFERRED/MANUAL typed results with raw UTF-8 source/generator provenance.
Only READY activates; DEFERRED is retried with native_frontmatter from the
later Node helper, never skipped as a native limitation. Unknown filters and
required unmapped fields have no agent row. Exact Read maps read+read_image;
native agentOptions preserves partial route overrides and JS safe integers.
Shared rule classification uses the unchanged original Codex source contract.
With isolated Poetry prefix, pytest tests/unit/test_dsh_render.py
tests/unit/test_frontmatter.py tests/unit/test_codex_render.py
tests/unit/test_rule_classify.py tests/unit/test_dsh_paths.py
tests/unit/test_dsh_targets.py tests/unit/test_shared_instructions.py
tests/unit/test_agents_md.py tests/unit/test_codex_targets.py
tests/unit/test_codex_install.py tests/integration/test_codex_target.py
tests/integration/test_codex_rule_drift.py -q: 411 passed in 0.46s,
142 new renderer cases. mypy src/: 76 files; Ruff/Black both owned files and
diff --check pass, all exit 0. No-index whitespace checks of new files emitted
no diagnostics (exit 1 for added diff). Native activation is a later gate.
