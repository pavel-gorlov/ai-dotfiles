---
id: ai-8n95c
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/scaffold/templates/dsh_bridge.mjs
- src/ai_dotfiles/scaffold/templates/dsh_audit.mjs
- src/ai_dotfiles/core/dsh_audit.py
- tests/integration/test_dsh_bridge.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
---

# Implement native literal prompt policy and readiness bridge

## Goal

Implement the necessary import-free native bridge and managed-row readiness audit using pinned public plugin APIs.

Size driver: Two native modules, Python audit data and real isolated bridge tests; the concern is native plugin activation.

## Scope and ownership

Mode: write. Phase 1 of approved epic ai-47xpm.
Implement Pre-decided decisions 7, 8, 12, 13; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/scaffold/templates/dsh_bridge.mjs
- src/ai_dotfiles/scaffold/templates/dsh_audit.mjs
- src/ai_dotfiles/core/dsh_audit.py
- tests/integration/test_dsh_bridge.py

## Definition of done

- [ ] Cordis file-URL plugins expose the named metadata/apply contract and retain stock child composition/spawn.
- [ ] Only exact whitelisted generated persona sections disable interpolation; literal DSH-only rule/description roster sections are appended and native schema descriptions retained.
- [ ] Known deny is monotonic; ask preserves downstream deny/cancel/ask and sandbox; child approval never rejects asks instead of granting them.
- [ ] Readiness waits for native Loader completion and checks every managed required id, reporting optional-plugin startup failures as activation failures.
- [ ] Focused pinned native fixtures verify literal braces/whitespace, PTC/both descriptions, inherited parent services, approval and readiness failures.
- [ ] Unsupported complete-persona or missing-provider modes fail with a reason rather than repairing a custom profile.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
