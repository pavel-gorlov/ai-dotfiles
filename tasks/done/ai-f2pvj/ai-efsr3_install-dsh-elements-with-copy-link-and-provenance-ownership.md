---
id: ai-efsr3
kind: subtask
status: done
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_install.py
- src/ai_dotfiles/core/fs_copy.py
- src/ai_dotfiles/core/symlinks.py
- tests/integration/test_dsh_target.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 2
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
- at: '2026-10-04T15:42:45+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T15:43:08+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T16:57:31+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Install DSH elements with copy link and provenance ownership

## Goal

Install rendered catalog elements through existing safe link/copy primitives with precise ownership and drift metadata.

Size driver: One target installer, reused filesystem primitives and install ownership tests.

## Scope and ownership

Mode: write. Phase 1 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 6, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_install.py
- src/ai_dotfiles/core/fs_copy.py
- src/ai_dotfiles/core/symlinks.py
- tests/integration/test_dsh_target.py

## Definition of done

- [x] Valid skill directories install natively in both scopes with safe symlink/copy behaviour and no Codex length transformation.
- [x] Rendered agents/rules/bridge resources carry source and generator provenance and foreign paths are preserved on collision.
- [x] Resources required for DSH exist even when Claude is not an installed target.
- [x] Install operations expose contributions/resources for later reconcile and prune; global writes stay under explicit roots or managed blocks.
- [x] Integration tests cover links, copies, user collisions, source/generator drift and idempotent installation.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** Previous six rows are committed and accepted; bridge
commit f7fb93f84dfe392a0a4237b53c65a739f27835a8 is verified clean. This is
the last Phase 1 row and the sole next writer. DSH preflight must preserve
foreign destinations and reject parent symlink escapes before reusing the
existing destructive copy/link primitives; their incumbent default behavior
is pre-existing, do not fix in this branch. No Phase 2 composition writes.

**to_do → wip.** tm ready reports only ai-efsr3 and tm next selects it;
parent ai-f2pvj and the explicit Phase 1 row order/holds are verified. Worker
owns only dsh_install.py, fs_copy.py, symlinks.py and test_dsh_target.py.
Read the complete tm context and approved epic/orchestrator. Gate: focused
install tests, DSH bridge/render/permissions/shared regressions, mypy and
Ruff/Black; coordinator will run the full Phase 1 regression barrier.
Materialize READY-only source/generator/resources with bounded ownership;
DEFERRED native YAML retry is injected/consumed by ai-ckvng, not guessed here.

**Phase 1 gate → fixture correction.** Coordinator full pytest collected
1652 tests: 1648 passed, four native-provider setup errors because
bridge_native_runtime was unavailable when test_dsh_bridge was collected
before test_dsh_target. Target-first focused 941/941 masked plugin registration
order. All-source mypy79/Ruff/Black163 pass. Task remains wip/unticked; same
worker corrects only owned test_dsh_target.py fixture exposure and repeats
full pytest plus bridge-first order, without skips or new source ownership.

**wip → done.** Actual three-file implementation diff reviewed. All 78
installer cases pass, including four real published RC2 project/global x
link/copy provider discovery/load tests, complete bundles/2400-char description,
resourceBase/invocation/executable bits, foreign collisions and full preflight,
copy/link transitions, source/support/generator drift, no-op bytes/mtimes,
READY retry/nonready provenance, shared union/current local protection, outer
aliases and wrapped I/O/source-change errors before mutation. Worker combined
941/941; corrected bridge-first 115/115; worker full 1652/1652 and coordinator
full 1652/1652 (8.86s, exit0). Coordinator mypy79/Ruff all/Black163 all pass.
safe_symlink adds chmod_scripts=True; DSH passes False to preserve source modes,
while existing callers retain defaults. fs_copy.py is reused unchanged.
Ownership schema/install generator 1; inventory covers exact per-entry source
and output trees/modes/link text, source SHA and generators. No aggregate
config/patch/hooks/profile writes or global scan. native_rows is a contribution,
not readiness. desired_output_keys/current_source_ids/retired_output_keys expose
old native outputs for later catalog/local-union retirement; launcher/reconcile
must retire or refuse stale READY-to-MANUAL/DEFERRED activation. Acceptance and
move will be staged with implementation; one verified commit remains required.
