---
id: ai-vv1t9
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_launch.py
- src/ai_dotfiles/commands/dsh.py
- src/ai_dotfiles/cli.py
- tests/unit/test_dsh_launch.py
- tests/e2e/test_dsh_launch.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 3
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
---

# Launch managed DSH with audited patches and environment

## Goal

Add the thin click-based ai-dotfiles dsh command and a core launcher for one project's audited native composition. This task owns click command integration and registration.

Size driver: One command/core pair, registration and argv/environment/activation tests.

## Scope and ownership

Mode: write. Phase 2 of approved epic ai-47xpm.
Implement Pre-decided decisions 3, 9, 12, 13, 14; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_launch.py
- src/ai_dotfiles/commands/dsh.py
- src/ai_dotfiles/cli.py
- tests/unit/test_dsh_launch.py
- tests/e2e/test_dsh_launch.py

## Definition of done

- [ ] Official executable/package and pinned API compatibility are resolved before readiness; missing runtime/providers and unsupported wrappers have actionable diagnostics.
- [ ] Global/current-project patches and environment launch the installed CLI without a shell; explicit user argv/env and native override order are preserved.
- [ ] User profiles/home patches/package files are unchanged; readiness failures prevent a false success report.
- [ ] One process remains bound to one project's MCP/hooks/agents; updates/project changes require restart and the command states this limitation.
- [ ] Exit status propagates correctly and new CLI help matches managed launch semantics.
- [ ] Tests cover no-shell argv, environment/bootstrap rules, native helper/audit failure and CLI help/restart notices.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
