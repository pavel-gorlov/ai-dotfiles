---
id: ai-pwjnx
kind: subtask
status: done
created_at: '2026-10-04T11:57:44+00:00'
parent: ai-f2pvj
context_files:
- pyproject.toml
- poetry.lock
- .pre-commit-config.yaml
- tests/integration/test_dsh_runtime.py
- README.md
dependencies:
- ai-7xrwf
executor_agent: claude
size: S
mode: read-only
phase: 9
status_history:
- at: '2026-10-04T11:57:44+00:00'
  status: backlog
- at: '2026-10-05T06:47:02+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T06:47:28+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T08:32:33+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Verify final DSH epic acceptance and existing regressions

## Goal

Run and record the epic's required final acceptance gates after all write subtasks are complete.

Size driver: Read-only integration verification of named suites and documentation; implementation fixes stay with their original owner.

## Scope and ownership

Mode: read-only. Phase 4 of approved epic ai-47xpm.
Implement Pre-decided decisions 11, 13, 15; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- pyproject.toml
- poetry.lock
- .pre-commit-config.yaml
- tests/integration/test_dsh_runtime.py
- README.md

## Definition of done

- [x] poetry run pytest --cov exits zero with coverage >=80%, including existing Claude/Codex lifecycle regressions.
- [x] The required pinned native runtime suite runs and passes with no acceptance skip.
- [x] poetry run mypy src/, poetry run ruff check src/ tests/, and poetry run black --check src/ tests/ pass.
- [x] Required pre-commit checks pass and git diff --check reports no whitespace issues.
- [x] CLI help, builtin skill, shipped examples and matrix acceptance agree; record exact gate evidence and any actual limitation.
- [x] Any failed gate returns to the responsible write owner before final acceptance is marked complete; this task edits no implementation files.

## Notes

This task is read-only; return gate evidence to the orchestrator and route corrections to the original write owner.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** All20 write children accepted and committed, last
bd7d8b0 independently verified exact7/all6 SHA and normal Git gates0; clean tree.
Queue sole final read-onlyS phase7 verification. Exact5 context files are reading
scope only; no implementation/tracker/Git edits. Full required gates and actual
documentation/matrix evidence remain all6 unchecked until root review.

**to_do → wip.** Actual ready confirms sole mode read-onlyS phase7 row.
Claim this ID directly; complete actual generated context/epic/current journal,
frozen-source required final gates. Six criteria stay open; report findings and
actual outputs without implementation, tracker or Git edits.

**Failed final audit → corrective hold.** Report
/private/tmp/dsh-pwjnx-report.json (SHAffff5ded1121e77619536eead6b2317773009c8817c86f5b8c7695e340244258)
proves full2426/native15 with0skips, coverage92.04%, mypy/Ruff/Black24.10 pass
on the original immutable cut. Required pre-commit Black25.1 then automatically
added one AST-identical comma in core/codex_rules.py and exited1. The auditor
stopped, retained that exact mutation and made no manual source/tracker/Git edits.
Supplementary isolated DSH-only add proves the generic Claude-only help false.
All six ticks stay open; source bytes changed so earlier passes do not replace
a fresh final gate. All auditor processes have ended. Hold this task idle wip
at the later phase9 barrier while sole corrective writer ai-fcbgs at8 validates
the exact comma and corrects add help. Resume only after its atomic commit is
independently verified, with whole fresh context and a new tracked-byte freeze.

**Corrective hold → fresh final verification.** Root independently verified
atomic0ff41f30f165509d40e0e1031be42f4bb0d83387 with parentbd7d8b0, exact7
raw paths/all6 live+HEAD SHA, corrective done4/4/usage, clean worktree and main
unchanged. Proof /private/tmp/dsh-fcbgs-root-commit-verified.json. Twenty-one
write children are accepted/committed; this sole read-only phase9 child resumes
without another lifecycle transition. Receive whole fresh actual tm context +
approved408-line epic + current entire journal. Freeze all tracked byte/mode/link
state including these two coordinator notes before every gate; stop on mutation.
Required fresh full2426/native15/no acceptance skip/coverage>=80% plus mypy/Ruff/
Black/precommit/whitespace and documentation matrix evidence. Actual pinned
Black source provenance is documented in corrective report; do not rebuild or
change tool/cache/dependency pins. Old failed report stays immutable. All six
criteria remain open until fresh report and root review; no source/tracker/Git
writes belong to the auditor. New report /private/tmp/dsh-pwjnx-final-report.json.

**wip → done.** Fresh PASS report /private/tmp/dsh-pwjnx-final-report.json
SHA2dd230cba282c0a487a425c9e203e8c243728c4c28c2b541159045e338515930,
51 actual gate/CLI records plus28 native records, all processes ended. Root
reviewed actual required argv/outputs/exits, current help and whole metadata-only
diff; independently verified all79 stream disk bytes/SHA, all2426 PASSED records,
JUnit2426/0fail/0error/0skip/native15 and XML9737/10579lines=92.04%. Fresh
mypy87/Ruff/Black182/six full precommit hooks/whitespace all0. Native9 positives
prove real child/current parent route/literal body+description/services retained/
deny+ask and Ready-before-turn; native6 negatives release no Ready/turn/child.
Selected Web trees contain all7 loaded/settled managed rows. Fresh wheel/sdist
contain byte-exact21 templates plus2 relevant source modules; installed CLI help
and child run outside checkout with no editable/PYTHONPATH fallback. Root live
proof preserves all342 worktree and260 main bytes/modes/index/HEAD/status plus
old failed report. Evidence /private/tmp/dsh-pwjnx-final-root-reviewed.json;
one scratch resource-count assumption was corrected only in the root probe
(23 rows include21 templates plus2 modules), with no gate/source change. Fresh
CLI/matrix13boundaries/examples and21 accepted child trace agree. Both prior
failures were routed/accepted/atomically committed before these fresh gates.
All six ticks now proven; normal acceptance/transition/validation and one final
metadata-only commit follow. Remote PR/CI publication and owner merge remain
orchestrator work; no claim of a remote run is made here.
