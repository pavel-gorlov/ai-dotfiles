---
id: ai-d80em
kind: subtask
status: done
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/shared_instructions.py
- src/ai_dotfiles/core/agents_md.py
- src/ai_dotfiles/core/codex_install.py
- tests/unit/test_shared_instructions.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 1
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
- at: '2026-10-04T13:08:58+00:00'
  status: to_do
- at: '2026-10-04T13:09:15+00:00'
  status: wip
- at: '2026-10-04T13:28:12+00:00'
  status: done
---

# Coordinate shared Codex and DSH instruction ownership

## Goal

Expose a narrow desired-block union for shared project instructions before any destructive lifecycle operation.

Size driver: One ownership coordinator, managed-block primitives and mixed-target tests.

## Scope and ownership

Mode: write. Phase 0 of approved epic ai-47xpm.
Implement Pre-decided decisions 2, 7, 10, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/shared_instructions.py
- src/ai_dotfiles/core/agents_md.py
- src/ai_dotfiles/core/codex_install.py (only remove_codex_rule_blocks delegation)
- tests/unit/test_shared_instructions.py

## Definition of done

- [x] Desired project blocks union enabled Codex/DSH catalog contributions and both local provenance registries.
- [x] Managed marker/source hashes stay compatible and user-authored Markdown survives updates and removal.
- [x] Existing Codex rule classification is preserved; DSH-only description rules are excluded from shared activation and routed through the DSH literal bridge.
- [x] The coordinator exposes the wanted/protected sets needed by install/remove/prune and empty-manifest cleanup.
- [x] Mixed-target tests cover single-target removal, local contributors, identical source blocks and source drift.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** Prior two Phase 0 rows are committed as 190b85d
and 2c8c2bc; target/path APIs and their gates are verified. Only the three
declared files belong to this owner. Codex rule classification is preserved;
DSH-only unconditional description rules stay outside shared Markdown.

**to_do → wip.** Selected by tm next --epic ai-47xpm in the explicit
Phase 0 sequence. Worker receives entire tm context and approved epic/
orchestrator; both local registry protection and byte-preserving user text
are required. Lifecycle consumers belong to later rows, not this writer.

**Initial ownership → shared-removal integration.** Coordinator authorizes
one narrow fourth-file change: codex_install.remove_codex_rule_blocks delegates
to the newline-preserving agents_md removal helper with the existing bool/error
contract. This implements decision 10 so existing Codex prune/remove callers
also preserve shared user Markdown. No other codex_install logic belongs here;
CLI dispatch remains with later lifecycle owners. DSH local rule_blocks uses
the same project-relative AGENTS.md-to-name-list schema as Codex.

**wip → done.** Actual four-file source/test diff inspected; ownership
and all five criteria are demonstrated. With isolated Poetry prefix:
pytest tests/unit/test_shared_instructions.py tests/unit/test_agents_md.py
tests/unit/test_rule_classify.py tests/unit/test_codex_targets.py
tests/unit/test_codex_install.py -q: 162 passed (51 new shared tests).
pytest tests/integration/test_codex_target.py
tests/integration/test_codex_rule_drift.py tests/integration/test_codex_reconcile.py
tests/integration/test_codex_migrate.py tests/e2e/test_codex_install.py
tests/e2e/test_codex_global.py -q: 78 passed. mypy src/: 75 source files;
Ruff/Black on four owned files and diff --check passed. Coordinator's full
pytest -q: 1249 passed in 4.19s; all commands exit 0. Shared paths are
canonical, DSH native layouts remain lexical. Local rule_blocks only protect
existing markers; local reconcile regenerates bodies. Command union consumers
and native bridge activation remain later gates.
