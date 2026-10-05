---
id: ai-gbrqm
kind: subtask
status: done
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/commands/status.py
- src/ai_dotfiles/commands/reconcile.py
- src/ai_dotfiles/commands/migrate.py
- src/ai_dotfiles/core/dsh_migrate.py
- tests/e2e/test_dsh_migrate.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 5
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
- at: '2026-10-05T01:47:04+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T01:47:40+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T02:12:43+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Wire DSH status reconcile and migration CLI

## Goal

Expose DSH drift/reconcile and project migration with consistent command output and completion.

Size driver: Three thin wrappers, fresh registered-original preservation and their CLI suite; Click Choice supplies target completion.

## Scope and ownership

Mode: write. Phase 3 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 5, 6, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/commands/status.py
- src/ai_dotfiles/commands/reconcile.py
- src/ai_dotfiles/commands/migrate.py
- src/ai_dotfiles/core/dsh_migrate.py
- tests/e2e/test_dsh_migrate.py

## Definition of done

- [x] status/reconcile and applicable -g/--check behaviour include DSH without losing existing Codex local-only behaviour.
- [x] migrate --to dsh and --dry-run are available in Choice/help/completion while preserving the existing default and project-only migration scope.
- [x] Errors and unsupported fields identify origin/reason through ui and core exception handling.
- [x] CLI tests verify drift exit status, check/dry-run zero-writes, migration classification and default/unknown-target regression.
- [x] Applicable existing command tests pass and no new global migration flag is introduced.

The first/fourth criteria include an existing registered local rule whose name
also belongs to a Codex catalog rule: full discovery must retain the original
while preserving manifest-name exclusions for unregistered catalog candidates.
Existing generic core/completions.py needs no target-specific write; this owner
proves --to dsh completion through the same Click Choice used by help/parsing.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**Catalog proof → full-discovery preservation boundary.** Atomic983d7bad is
verified, clean and frozen. Actual independent catalog install with different
Codex namesake body refuses Conflicting shared target union before changing
the registered local DSH block. Subsequent full reconcile --check incorrectly
labels AGENTS.md/shared and its local source retired, despite the original
.claude/rules/shared.md still existing: generic manifest-name exclusion hides
it. Add dsh_migrate.py's narrow registered-original exception to full discovery;
retain existing generic local_discovery policy and exact catalog link/copy
filters. Free the completion slot because Click Choice supplies --to values;
prove it in the same CLI suite. Five files/five criteria, same approved scope.

**Producer overlap → ordered scheduling subphase.** Run this CLI group and
ai-b8jes at phase5 after completed migration/catalog phase4; final milestone
uses phase6. Approved five milestones/one PR remain unchanged; this extra
internal barrier orders producer writes without a three-node dependency chain.
Whole-cut fresh critic/cut-check must pass before promotion or source edits.

**Discovery cut → cleared promotion.** Fresh whole-cut critic reads23 files and
all21 children, checks1–7 PASS, findings0/BLOCKING0; actual cut-check exit0
with empty stderr. Exact report /private/tmp/dsh-gbrqm-cut-critic-report.json.
Five-file producer/CLI ownership and unchanged approved scope are confirmed.

**ai-gbrqm backlog → to_do.** Critic-cleared five-file CLI/producer owner
queued after atomic983d7bad; preserve namesake original, existing default Codex
and project-only migrate. Readiness must confirm phase5 before dispatch.

**ai-gbrqm to_do → wip.** Actual ready/next selects the only permitted
phase5 modewrite row under ai-f2pvj. Dispatch one current-model owner with
whole generated context/epic/journal, exact five paths and five open criteria.
No other source writer/read fan-out; required source/test/static evidence and
coordinator review precede ticks or commit. Generic discovery exclusions remain
except live recorded originals; guarded value activation stays ai-wkpk8.

**Frozen CLI implementation → reviewed evidence / full-loopback hold.**
Coordinator inspected complete final five-file diff +884/-35 SHA0324da7b,
including all637 owned test lines; final five source SHA match worker freeze
and root review. Worker own49/49, affected18-suite384/384 exit0; root independent
own49/49 in10.23s, two-case live namesake check/raw bytes/mode/mtime probe0,
mypy87/Ruff5/pinned Black25.1 five all0. Equal body has no false drift;
different body refuses shared union before writes; catalog provenance exclusion,
deleted-source retirement, native/hooks/MCP retention and default/project-only
Choice remain demonstrated. Existing Codex full local discovery/aggregate exit
is retained even with disabled catalog target. Initial whole2332 gate has only
2 isolated-loopback EPERM failures/2330pass, stderr empty; unchanged command
repeated with require_escalated, session76119 still running. Five ticks remain
open until complete full stdout/stderr/exit. Evidence root-reviewed JSON,
owned diff and worker logs under /private/tmp/dsh-gbrqm*.

**Full-loopback hold → verified five-criterion acceptance.** Exact whole
pytest command with pinned RC2 now2332/2332 in130.01s, exit0, stderr empty;
coordinator reads complete successful stdout and both attempts, final report,
initial fixture/import corrections and all5 SHA. No excluded/skipped tests or
source edits between attempts. Successful log
/private/tmp/dsh-gbrqm-logs/1791166166057405000.json; complete report
/private/tmp/dsh-gbrqm-report.json. Combined owned diff SHA0324da7b matches
independent root review, source5 frozen. Criteria1 project/global DSH drift and
live namesake/local-only Codex;2 actual Choice/help/completion/default and no-g;
3 origin/field/reason/classifications/refusals;4 bytes/link/mode/mtime snapshots,
resource/generator drift and deletion;5 affected384/full2332 all demonstrated.
Native host final matrix and supported guarded-value join remain later owners.
Five ticks now reflect inspected evidence; prepare same-commit move/usage.

**ai-gbrqm wip → done.** Actual acceptance5/5 and move done exit0,
usage written. Source5 plus this task relocation/ticks, orchestrator journal
and six future-task phase-only recut records form one15-path transaction.
Hold ai-b8jes until parent983d7bad, exact frozen5 SHA/allowlist, successful
hooks/msg and clean worktree/main preservation are independently verified.
