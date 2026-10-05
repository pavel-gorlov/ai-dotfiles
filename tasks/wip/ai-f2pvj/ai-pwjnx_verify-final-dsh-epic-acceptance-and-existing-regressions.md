---
id: ai-pwjnx
kind: subtask
status: wip
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

- [ ] poetry run pytest --cov exits zero with coverage >=80%, including existing Claude/Codex lifecycle regressions.
- [ ] The required pinned native runtime suite runs and passes with no acceptance skip.
- [ ] poetry run mypy src/, poetry run ruff check src/ tests/, and poetry run black --check src/ tests/ pass.
- [ ] Required pre-commit checks pass and git diff --check reports no whitespace issues.
- [ ] CLI help, builtin skill, shipped examples and matrix acceptance agree; record exact gate evidence and any actual limitation.
- [ ] Any failed gate returns to the responsible write owner before final acceptance is marked complete; this task edits no implementation files.

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
