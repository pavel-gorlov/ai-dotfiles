---
id: ai-47xpm-2
epic: ai-47xpm
kind: decision
created_at: '2026-10-03T20:07:58+00:00'
status: accepted
impact:
- ux
- time
---

# Project and global DSH scopes

## Context

Q2 offered project+global lifecycle or a smaller project-only first delivery.
The owner selected "2. Project + global".

## Decision

Support project and user scope in the same DSH-target epic, honouring DSH_HOME
and preserving user-owned shared files in both scopes.

## Alternatives considered

- Project-only first PR: rejected by the owner; global support is required now.
- Unbounded traversal of the user home: unnecessary; manage explicit DSH artefacts.

## Consequences

Answered by owner at Q2. Include global catalog commands, provenance/drift,
bounded pruning, instruction bridging, and composition with project contributions.
Tests must isolate DSH_HOME and cover both scopes and their coexistence.
