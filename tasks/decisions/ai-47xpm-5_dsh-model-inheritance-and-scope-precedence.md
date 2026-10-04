---
id: ai-47xpm-5
epic: ai-47xpm
kind: decision
created_at: '2026-10-04T07:20:28+00:00'
status: accepted
impact:
- ux
- irreversible
---

# DSH model inheritance and scope precedence

## Context

Claude-only agent model aliases have no faithful native provider/model mapping.
Review also required explicit scope precedence and public-name conflict policy.
The Q2 question stated project-over-global precedence for managed agent/MCP names,
refusal of conflicts with user names, and ownership coordination inside the
already accepted size L estimate. The owner answered "брать текущую модель"
on 2026-10-04.

## Decision

Use the current parent DSH session model route for Claude-only aliases, retaining
the alias in provenance and reporting MODEL_UNMAPPED. Compose global before
project; project wins for the same managed agent/MCP name. A conflicting user
id/tool/serverName stops activation instead of being renamed or overwritten.

## Alternatives considered

- MANUAL until a native route is configured: rejected; the owner wants current
  session model inheritance and agents available without that setup.
- Guessing a provider/model from a Claude alias: cannot preserve native routing.
- Silently renaming or overwriting user rows: excluded by the accepted question's
  explicit ownership policy.

## Consequences

Answered by owner at Q2. Native routes supplied in dsh.fragment.json remain
explicit; omitted/inherit models also use the current parent route. A model
change in the parent session is inherited when the native child is spawned.
The namespace, merge order and ownership tests are part of existing scope L,
including the narrow shared_instructions.py coordinator; no new product surface
or generic adapter framework is added.
