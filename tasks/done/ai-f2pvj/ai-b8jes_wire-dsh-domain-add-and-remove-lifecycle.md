---
id: ai-b8jes
kind: subtask
status: done
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/commands/domain.py
- src/ai_dotfiles/core/dsh_migrate.py
- tests/e2e/test_dsh_domain.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 6
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
- at: '2026-10-05T02:22:35+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T02:23:05+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T03:10:17+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Wire DSH domain add and remove lifecycle

## Goal

Route domain mutations through selected-target collectors in project and global scope.

Size driver: One domain wrapper, bounded existing core retirement helpers, and
multi-domain/scoped CLI regressions for reversible source custody.

## Scope and ownership

Mode: write. Phase 3 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 4, 5, 9, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/commands/domain.py
- src/ai_dotfiles/core/dsh_migrate.py
- tests/e2e/test_dsh_domain.py

## Definition of done

- [x] Domain add/remove respects selected DSH targets and both catalog scopes instead of assuming Claude-only installation.
- [x] Native fragments, agent/MCP rows, hooks and copied resources enter/retire through core collectors with source ownership.
- [x] Adding a second domain retains the first; removing one preserves other domains and user contributions.
- [x] Existing dependency/runtime bin machinery is reused and update/vendor/pull stay catalog-only.
- [x] New CLI tests exercise DSH-only/mixed-target domain mutations, dependency order, collisions and both scopes.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**ai-b8jes backlog → to_do.** Previous CLI child committed/verified
at8f7d871b, whole2332 gate green. Queue exact2-path domain lifecycle owner;
actual readiness/next must confirm phase5 before source dispatch.

**ai-b8jes to_do → wip.** Actual ready/next selects the only permitted
phase5 modewrite row. Dispatch one current-model owner with entire generated
context/approved epic/current journal and exact2 paths. Five criteria open;
selected project/global DSH targets and source/resources/shared ownership must
be demonstrated through pure core collectors and existing machinery. Return
any actual extra source boundary before writing it; no overlapping writers.

**Two-file boundary → bounded three-file retirement owner.** Actual disposable
probes exit0 show current Codex classification survives source deletion, and
current DSH preflight can pass while desired retirement refuses unproven shared
custody. Source/test edits remained empty. Add only core/dsh_migrate.py for a
typed reversible catalog-source staging context manager and keyword-only
precollected CodexRulePlan input to the existing removal helper. Default callers
keep their contracts; the surviving union is freshly recomputed after staging.
Stage outside catalog/resource trees; preflight every affected scope before
first target write, restore the source on refusal, and clean temporary custody
on success. No callback framework, flag, source format or user decision.
The prior lifecycle owner shares this helper; separate its completed barrier
from this owner rather than adding a three-node dependency chain. Whole-cut
fresh critic/cut-check and full updated context are required before any edit.

**Fresh critic → three-file implementation resumed.** All23 task files fully
reviewed; checks1–7 PASS/BLOCKING0, actual cut-check0, validation49/33legacy0.
Same owner/current model receives whole regenerated context; exactthree paths
above. Acceptance stays open; preserve other edits and return any further actual
write boundary before editing it. Source staging must restore on refusal across
all affected scopes before target mutation.

**Frozen archived worker → available current-model worker.** Host thread limit
prevents prior-owner resumption/new spawn. Available launcher worker receives
the same full3058-line context, exactthree paths and openfive criteria as sole
writer. No source changes by prior worker; no scope/gate/model changes.

**Frozen result → coordinator acceptance.** Entire three-file diff (+804/-121),
all372 test lines and allfive criterion proofs read. Worker own62/affected413/
full2372 exit0; complete commands/stdout/stderr read, mypy87/Ruff3/Black3/
whitespace0. Initial test assertions corrected to actual row.id/native patches
and empty hooks metadata with beta-only origin; contribution is None, no removed
handler row. Two known sandbox127.0.0.1 EPERM repeat identical gates with isolated
loopback permission, no exclusion. Root independent62/62 and two CLI probes0:
missing historical custody in later scope refuses desired retirement after
current preflight passes, restores source bytes/mode/mtime and ALL project/global
file+directory bytes/modes/mtimes; proved retirement removes Codex blocks while
raw CRLF user text survives both scopes. Source threeSHA match frozen report;
root-review /private/tmp/dsh-b8jes-root-reviewed.json. Allfive ticks demonstrated.

**ai-b8jes wip → done.** Actual tm acceptance5/5 exit0 then tm move done
exit0. Prepare source3, task ticks/rename, usage journal and five future bounded
cut records in the same transaction; no source changes after frozen SHA.
Git executor must verify HEAD parent8f7d871b, exactallowlist, pinnedprecommit
and commit-msg/whitespace0, unchanged3 SHA and clean tree before nextdispatch.
No final contract/PR readiness claim yet; five final children remain queued.
