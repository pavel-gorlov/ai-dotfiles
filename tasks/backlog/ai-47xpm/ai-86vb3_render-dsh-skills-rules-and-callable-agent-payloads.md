---
id: ai-86vb3
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_render.py
- tests/unit/test_dsh_render.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
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

- [ ] Native skill names, descriptions and invocation fields are validated without Codex description truncation.
- [ ] Shared always-on rule payloads and DSH-only literal description-rule sections preserve source bodies; path-scoped activation gaps are reported.
- [ ] Each supported agent emits one uniquely named native subagent-tool row with literal persona, description, known child filters and retained source provenance.
- [ ] Unknown/unrepresentable tool restrictions make the affected agent MANUAL instead of unrestricted.
- [ ] Omitted/inherit and Claude-only aliases use the current parent session route; aliases emit MODEL_UNMAPPED; native routes stay explicit.
- [ ] Renderer tests cover braces/whitespace, invalid input, diagnostics by origin and no invented provider/model identifiers.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
