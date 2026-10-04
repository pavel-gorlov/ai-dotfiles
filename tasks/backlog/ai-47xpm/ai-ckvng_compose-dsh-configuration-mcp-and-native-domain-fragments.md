---
id: ai-ckvng
kind: subtask
status: backlog
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_config.py
- src/ai_dotfiles/core/dsh_native.py
- src/ai_dotfiles/scaffold/templates/dsh_compose.mjs
- tests/unit/test_dsh_config.py
- tests/integration/test_dsh_config_drift.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
---

# Compose DSH configuration MCP and native domain fragments

## Goal

Collect and validate one effective configuration snapshot using the Node composition helper and native APIs, including named MCP and domain patch contributions. This task owns the Node helper integration.

Size driver: Collectors, one native helper and configuration/ownership tests within five files.

## Scope and ownership

Mode: write. Phase 2 of approved epic ai-47xpm.
Implement Pre-decided decisions 4, 9, 11, 12, 13, 14; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_config.py
- src/ai_dotfiles/core/dsh_native.py
- src/ai_dotfiles/scaffold/templates/dsh_compose.mjs
- tests/unit/test_dsh_config.py
- tests/integration/test_dsh_config_drift.py

## Definition of done

- [ ] dsh.fragment.json is a domain-root JSON native patch array; existing dependency ordering and source-relative plugin/resource bindings are retained.
- [ ] The exported native composition APIs inspect profile/home/CLI ordering without invoking dump-config or writing user profile files; Python does not evaluate YAML/!!js.
- [ ] MCP stdio/streamable-http preserve serverName, cwd/args/env/headers; unsupported SSE/prompt semantics and unprovable dynamic conflicts are diagnosed.
- [ ] Global then project produces one managed logical name; user-row collisions stop activation; adding/removing one domain preserves other contributions.
- [ ] Environment collection preserves explicit process env precedence and rejects reserved DSH bootstrap variables.
- [ ] Source/generator/contribution drift, full-config replacement and expression/conflict refusal are covered by the new tests.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.
