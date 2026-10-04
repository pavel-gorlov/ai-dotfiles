---
id: ai-nzmc8
kind: subtask
status: done
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_migrate.py
- src/ai_dotfiles/core/dsh_local_registry.py
- src/ai_dotfiles/core/local_discovery.py
- tests/integration/test_dsh_migrate.py
- tests/integration/test_local_discovery.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 4
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
- at: '2026-10-04T22:54:47+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T22:55:11+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T23:32:18+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Migrate local Claude elements with DSH source registry

## Goal

Discover and classify project-local sources and retain enough provenance for later retirement/reconciliation.

Size driver: Migration, local registry and discovery boundaries with copy-mode regressions.

## Scope and ownership

Mode: write. Phase 3 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 6, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_migrate.py
- src/ai_dotfiles/core/dsh_local_registry.py
- src/ai_dotfiles/core/local_discovery.py
- tests/integration/test_dsh_migrate.py
- tests/integration/test_local_discovery.py

## Definition of done

- [x] Local skills/agents/rules/commands/settings/settings.local/.mcp.json/hooks classify as MECHANICAL/REFACTOR/MANUAL through the approved matrix.
- [x] Catalog domain symlinks and copy-owned paths are excluded from local discovery.
- [x] Registry records outputs, contributions and resources by source with source/generator provenance.
- [x] Dry-run writes no bytes, including activation/profile snapshots, and reports origin/field/reason for gaps.
- [x] Discovery and migration tests cover copy mode, foreign files, unsupported restrictions and project-only scope.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** Prior managed-launch commit1976ead5 verified against
parent23610458: exact9paths, source/ticks/move/usage together; own47, relevant871
and static/Git gates all exit0, no formatter mutations, clean worktree/main
preserved. Phase3 gate is green. Queue only this five-file migration owner;
local original-source/provenance producer and zero-write dry-run are required.
Launcher integration awaits this concrete API and a later bounded continuation.

**to_do → wip.** tm ready and tm next select ai-nzmc8, parentai-f2pvj,
modewrite phase4. One current-model worker receives the entire generated context,
approved epic and orchestration journal with exact five-file ownership. No
concurrent writer/read fan-out. Produce fresh typed raw configuration/render
inputs for later lifecycle/launch consumers, without touching their owned files.
All five acceptance criteria remain open pending actual evidence/review.

**Producer API review → guarded-value integration hold.** Existing public
DshConfigSource and DshHookSource accept path only and reread aggregate JSON.
Owned .claude/settings.json/.mcp.json user-only projections cannot be supplied
faithfully without another guarded-value boundary; a disk snapshot would break
dry-run and aggregate replay would duplicate catalog entries. Same five-file
owner continues discovery/registry/render and unowned original inputs; expose
fresh typed original path/hash, user-only value and ledger guards for affected
sources. Diagnose these as a concrete REFACTOR/integration hold, not impossible
native semantics. No private collector call, temporary source snapshot, flag or
new schema guess. Coordinator budgets config/hooks/launcher/migration join before
final acceptance once the actual producer API exists. Local launcher refuses
registry until that join; whole-epic local activation remains open.

**Original ledger review → ambiguous-field boundary.** settings_ownership
tracks permission strings/hook signatures but not env/scalar origin. strip_owned
therefore proves only its tracked local view; matching current catalog values
cannot prove user intent. Preserve fresh original hash/value/ledger guards and
explicit unproven_fields. Later guarded-value join must not activate retained
ambiguous env/scalars as user-only. MCP ownership identifies server origins.
This actual original-provenance limitation is separate from the temporary API
hold; keep supported tracked projections, exact field diagnostics and user bytes.

**Concrete producer → lifecycle hand-off.** collect_dsh_local_inputs accepts
fresh catalog_plan/native_frontmatter and returns ONE merged install plus
guarded raw_sources/config_sources/hook_sources. plan_dsh_migration composes
original catalog/global sources with one hooks contribution. Missing fresh
catalog_plan with recorded catalog inventory refuses rather than overwriting
other contributions. Shared local-rule refresh is held for next ai-m4s7p's
verified own-source custody and in-memory union plan; never delete/change the
protection registry temporarily to bypass an installer collision. This is the
later lifecycle gate, not broader write ownership for this five-file worker.

**Initial74 gate → original-presence correction.** Own74 cases and two real
native tests pass; coordinator bounded TemporaryDirectory probe then collects
raw_sources0, creates .claude/settings.local.json with deny Bash, and observes
verify_dsh_local_inputs still accepts the stale source set. Same five-file owner
adds finite original absence/presence guards or source-set equality and a failure-
before-write regression. No repository sweep or extra boundary. All five leaf
criteria remain unticked until the updated frozen native/regression/static gate.


**Frozen producer → acceptance proof.** Exact five owned files reviewed;
worker native RC2 / relevant regression command passes1045/1045 (15.62s), exit0,
no skips. Coordinator independently passes own80/80 (1.34s), including real native
flat-command/frontmatter checks, exit0; mypy86, Ruff5, Black5 and whitespace
checks exit0. Source-set absence/presence correction rejects each newly created
original before writes. Registry validates source/output generator provenance,
retains READY-to-MANUAL custody and returns isolated snapshots; catalog copies
and linked domain parents are excluded. All five producer criteria are proven.
Supported owned projections remain the explicit ai-wkpk8 integration boundary;
unproven env/scalar provenance remains an exact MANUAL diagnostic. Lifecycle
refresh/retirement belongs to ai-m4s7p, with in-memory union protection required.
Frozen diff artifact: /private/tmp/dsh-orchestration-contexts/ai-nzmc8-frozen-five.diff,
sha2565c6092b9998f2dfbf211f3ab48d896e6a9683885049284ac8dde536d91165e90.

**21-child cut → accepted continuation.** Fresh-context critic reads the whole
epic/orchestrator and all21 children, checks1–7: BLOCKING0. Its actual tm cut-check
ai-f2pvj exits0, stdout '+ ai-f2pvj: cut-check passed', stderr empty. Coordinator
same structural check/validate pass. ai-wkpk8 remains backlog until all Phase4
owners finish; no Q3/scope change or concurrent source writer.

**wip → done.** tm acceptance5/5 and tm move ai-nzmc8 done exit0; usage
snapshot and relocation are prepared with source/ticks/journal for one commit.
No source writer starts before the coordinator verifies that commit.
