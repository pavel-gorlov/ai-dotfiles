---
id: ai-f2bcb
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- tests/integration/test_dsh_runtime.py
- tests/conftest.py
- pyproject.toml
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 6
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
---

# Build required isolated pinned DSH runtime acceptance

## Goal

Own the pinned native runtime fixture, provider setup and shipped-helper packaging gate required by the epic.

Size driver: A real disposable runtime smoke suite, shared isolation fixtures and packaging/test marker configuration.

## Scope and ownership

Mode: write. Phase 4 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 7, 8, 12, 13, 15; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- tests/integration/test_dsh_runtime.py
- tests/conftest.py
- pyproject.toml

## Definition of done

- [ ] The exact @deepseek-ai/dsh@0.2.0-rc.2 baseline is installed/resolved only in a disposable fixture with isolated homes and local fake provider/MCP/hook programs.
- [ ] Startup waits for managed required ids and invokes a real named child tool; retained parent services, current model route, literal bodies/descriptions and deny/ask including child approval are verified.
- [ ] Native full-config precedence, MCP/hook activation and a failing optional managed plugin produce the expected audited behaviour.
- [ ] No production credentials, external provider requests or real home files are used; unavailable runtime setup fails the required gate instead of skipping.
- [ ] Generated ESM helpers are included in wheel/sdist; required markers/resources are configured and isolated installed-CLI verification passes.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
