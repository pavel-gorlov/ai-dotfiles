---
id: ai-47xpm-1
epic: ai-47xpm
kind: decision
created_at: '2026-10-03T20:07:58+00:00'
status: accepted
impact:
- ux
- time
---

# Full feasible DSH target

## Context

Q2 offered a native-file MVP (M) or expanded Cordis integration (L,
approximately 2–3 times the scope). The owner answered:
"1. расширенный - полный возможный. 2. Project + global".

## Decision

Deliver the maximal faithful DSH target supported by the pinned upstream:
skills, instructions/rules, agent presets, hooks, MCP, supported settings,
and complete applicable ai-dotfiles lifecycle; document semantic gaps explicitly.

## Alternatives considered

- Native-file-only MVP: rejected by the owner because it omits feasible DSH surfaces.
- Unlimited runtime fork or lossy compatibility: not implied by full support;
  preserve permission and activation semantics and bound work to the adapter.

## Consequences

Answered by owner at Q2. Re-research profiles and native plugin activation,
rewrite the existing epic as size L, and include required DSH-specific generation.
New material UX forks still need concrete Q2 choices; review and Q3 follow.
