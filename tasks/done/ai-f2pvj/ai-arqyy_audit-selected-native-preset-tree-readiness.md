---
id: ai-arqyy
kind: subtask
status: done
created_at: '2026-10-04T19:12:04+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/scaffold/templates/dsh_audit.mjs
- src/ai_dotfiles/core/dsh_audit.py
- tests/integration/test_dsh_bridge.py
executor_agent: claude
size: M
mode: write
phase: 3
status_history:
- at: '2026-10-04T19:12:04+00:00'
  status: backlog
- at: '2026-10-04T19:36:21+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T19:36:44+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T19:52:50+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
dependencies:
- ai-7xrwf
---

# Audit selected native preset tree readiness

## Goal

Audit the real selected native PresetTree after Loader settlement, so loaded
managed scoped rows pass and missing/failed/disabled scoped rows refuse readiness.

Size driver: Three tightly related audit/generator/regression files under the
existing readiness contract; public selected-tree enumeration must be proven.

## Scope and ownership

This is a bounded integration correction to ai-8n95c's existing audit, discovered
by ai-ckvng's real RC2 preset host test. Implement epic decisions 7, 11, 12, 13;
no new surface, runtime, fallback, permission or user choice is introduced.
ai-8n95c remains done. ai-ckvng stays wip and its worker must be idle while this
corrective writer runs; later hooks/launch remain held. The coordinator owns the
one same-transaction commit and all tracker edits.

## Context files

- src/ai_dotfiles/scaffold/templates/dsh_audit.mjs
- src/ai_dotfiles/core/dsh_audit.py
- tests/integration/test_dsh_bridge.py

## Definition of done

- [x] Native audit awaits and enumerates the actual selected PresetTree with the root Loader through public APIs; loaded scoped managed rows are found without a fake Loader or durable synthetic Session/Agent.
- [x] Missing, disabled, failed, pending or ambiguous scoped required rows remain fatal; foreign optional rows remain diagnostics and exact agent body/filter/options checks are preserved.
- [x] Audit template and Python generator metadata are incremented together; stale generated modules/configs require regeneration with the existing ownership mechanism.
- [x] Real pinned RC2 scoped audit tests cover success/failure and existing bridge, global and parent/child composition regressions pass; helper readiness commits only after the scoped audit passes.

## Notes

The existing audit enumerates only ctx.loader.entries(), but a native PresetTree
is detached from that root tree. The real RC2 probe exposes the selected tree
through the public ctx.fiber.entry.parent.tree relationship. Prove that path
and Loader/tree await behavior; inspect service scope and deduplicate entry
objects before id matching. Never fake root entries or weaken missing-row checks.
Preserve global audit behavior and actual child inheritance. Use disposable
runtime /private/tmp/dsh-bridge-native-rc2 and isolated homes only.

You are not alone in the codebase: preserve all other owners' edits. Own only
the three context files; do not modify ai-ckvng's five files, tracker or Git.

## Execution notes

**Native scoped failure → bounded corrective cut.** ai-ckvng's published RC2
composition suite passes 91 cases, but two actual preset readiness cases expose
missing scoped rows in the existing audit. This additional child isolates the
correction within three files and the approved five-file dispatch limit. Owner
Q3 and epic scope stay valid; acceptance remains open until native proof.

**backlog → to_do.** Fresh-context corrective critic read the epic, orchestrator
and all 20 children: BLOCKING: 0; tm cut-check ai-f2pvj exit 0 with complete
stdout/stderr evidence. Earlier phases 1–2 are done; ai-ckvng is held wip with
its writer idle. Queue this disjoint three-file correction as the sole writer.

**to_do → wip.** tm ready and tm next select ai-arqyy, mode write, phase 3,
parent ai-f2pvj, without overlap with held ai-ckvng. One worker receives the
whole deterministic context plus approved epic/current contract and exact
three-file ownership. Required native checks retain the two real selected-preset
assertions in ai-ckvng's test file; those five files remain read-only to this
worker. Prove strict root/selected-tree union and generator drift together.

**wip → done.** Actual three-file diff reviewed; all four criteria demonstrated.
Worker native/render/policy/installer regressions 415/415 and config/scoped
67/67 pass. Coordinator independently ran the entire bridge suite plus both
unchanged ai-ckvng scoped tests: 51/51, exit 0 (5.18s). mypy81, owned Ruff/Black2,
Node syntax and whitespace gates exit 0. Native serviceFor plus exact public
Impl.value/Fiber/Entry identity proves the selected tree; its await/entries are
unioned with settled root Loader and deduplicated by object. Both public root
export and scoped service run agree; unproved tree fails SCOPED_TREE_UNAVAILABLE.
Audit generator is 2 in Python/ESM, schema/bridge/policy stay 1. Stale audit
module/config require regeneration together. Twelve added tests cover delayed
startup, actual child inheritance, absence of synthetic sessions, all strict
failure classes, unselected exclusion and ownership generator drift. Root owns
the same-transaction commit with tracker cut/journal/usage; config source remains
uncommitted with its original acceptance open until resumed owner closes edges.
