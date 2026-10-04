---
id: ai-47xpm-4
epic: ai-47xpm
kind: decision
created_at: '2026-10-04T06:33:50+00:00'
status: accepted
impact:
- ux
- time
- irreversible
---

# Native DSH fragment format

## Context

Native DSH settings need fields without Claude equivalents.
Q2 offered dsh.fragment.json or only exact transformations of Claude files.
The owner selected "2. добавить" on 2026-10-04.

## Decision

Add a domain dsh.fragment.json top-level JSON array of native Cordis patches,
including native full-config replacement semantics rather than deep merge.

## Alternatives considered

- No native fragment: rejected; it omits explicit provider/model and plugin configuration.
- Encoding native data as a Claude settings translation: misleading and unnecessary.

## Consequences

Answered by owner at Q2. This is a new public catalog format: document and validate
its JSON data, origin/precedence, targets and lifecycle. Include schema/collector tests.
Do not introduce executable YAML expressions or silently approximate Claude aliases.
