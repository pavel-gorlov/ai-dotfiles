---
id: ai-47xpm-3
epic: ai-47xpm
kind: decision
created_at: '2026-10-04T06:33:50+00:00'
status: accepted
impact:
- ux
- time
---

# Managed DSH launch

## Context

Expanded DSH support needs active native plugin rows in addition to files.
Q2 offered a managed launcher or integration into user profiles/bundles.
The owner answered "1. Управляемый запуск 2. добавить" on 2026-10-04.

## Decision

Use ai-dotfiles dsh to compose global/current-project contributions and launch
the installed DSH with generated --patch, without modifying user profiles.

## Alternatives considered

- Persistent profile/bundle edits: rejected; they add shared-file/dependency ownership.
- Bare native-file installation: cannot activate the chosen plugin-backed surfaces.

## Consequences

Answered by owner at Q2. Include launcher, native composition inspection and audit.
The accepted question states one process per project and restart for changes;
Web workspace switching does not retarget MCP/hooks. Preserve explicit CLI/env input.
