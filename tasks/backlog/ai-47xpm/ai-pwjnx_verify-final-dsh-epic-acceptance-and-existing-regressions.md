---
id: ai-pwjnx
kind: subtask
status: backlog
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
phase: 5
status_history:
- at: '2026-10-04T11:57:44+00:00'
  status: backlog
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
