---
id: ai-8n95c
kind: subtask
status: done
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/scaffold/templates/dsh_bridge.mjs
- src/ai_dotfiles/scaffold/templates/dsh_audit.mjs
- src/ai_dotfiles/core/dsh_audit.py
- tests/integration/test_dsh_bridge.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
- at: '2026-10-04T14:18:21+00:00'
  status: to_do
- at: '2026-10-04T14:18:40+00:00'
  status: wip
- at: '2026-10-04T15:29:27+00:00'
  status: done
---

# Implement native literal prompt policy and readiness bridge

## Goal

Implement the necessary import-free native bridge and managed-row readiness audit using pinned public plugin APIs.

Size driver: Two native modules, Python audit data and real isolated bridge tests; the concern is native plugin activation.

## Scope and ownership

Mode: write. Phase 1 of approved epic ai-47xpm.
Implement Pre-decided decisions 7, 8, 12, 13; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/scaffold/templates/dsh_bridge.mjs
- src/ai_dotfiles/scaffold/templates/dsh_audit.mjs
- src/ai_dotfiles/core/dsh_audit.py
- tests/integration/test_dsh_bridge.py

## Definition of done

- [x] Cordis file-URL plugins expose the named metadata/apply contract and retain stock child composition/spawn.
- [x] Only exact whitelisted generated persona sections disable interpolation; literal DSH-only rule/description roster sections are appended and native schema descriptions retained.
- [x] Known deny is monotonic; ask preserves downstream deny/cancel/ask and sandbox; child approval never rejects asks instead of granting them.
- [x] Readiness waits for native Loader completion and checks every managed required id, reporting optional-plugin startup failures as activation failures.
- [x] Focused pinned native fixtures verify literal braces/whitespace, PTC/both descriptions, inherited parent services, approval and readiness failures.
- [x] Unsupported complete-persona or missing-provider modes fail with a reason rather than repairing a custom profile.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** The two Phase 1 producers are committed and
verified: renderer 1baa6da and permissions 79c9d8c. Permission schemaVersion
1/generator 1 requires rejection of blocked/unknown-schema/malformed data;
source diagnostics/provenance and repeated origins survive collector merge.
This owner supplies actual native bridge/readiness evidence on pinned RC2,
without custom-profile repair or a replacement subagent runtime.

**to_do → wip.** tm next selected this exact next Phase 1 row.
One native bridge worker receives the entire generated context and approved
epic/orchestrator. Ownership is exactly two ESM templates, dsh_audit.py and
test_dsh_bridge.py. The focused fixture must install/resolve exact RC2 only
under a disposable root with isolated DSH/agents homes and fake services;
missing runtime setup fails rather than skips. No production home/profile,
credentials or external model/service requests are permitted or needed.

**In-progress → infrastructure retry.** Worker reported 10 focused cases
on real published RC2 (including named child, current route, literal CRLF,
native/PTC/both, monotonic deny and native approval never), then its turn
failed with Selected model is at capacity. Continued the same worker/model
with existing four owned files; do not restart or mark accepted. Runtime
scratch /private/tmp/dsh-bridge-native-rc2 holds exact RC2; remaining scoped,
readiness/filter/complete/malformed cases and final gates are still pending.

**wip → done.** Coordinator inspected all four final files and confirmed
37 focused tests on exact published RC2, exit 0 (36 execute native runtime,
one tests the builder). Worker final combined gate: 596 passed in 4.70s,
including 559 renderer/permission/path/shared/Codex regressions; mypy78,
Ruff/Black2, both node --check and whitespace pass. Actual Loader file-URL
activation, named child invocation/current route, CRLF/literal bodies,
PTC/both descriptions, scoped parent preset/service inheritance, native
approval never and sandbox are proven. Managed optional import/apply/pending/
missing/disabled failures, exact filter mutation, malformed policy, complete
persona and missing provider refuse readiness. Foreign optional failures
remain diagnostics. build_bridge_config and bridge_audit_requirements are
public producer contracts; schema/generators 1/1, filter/options snapshots
are independent. Module materializers carry template SHA and managed signature.
Host must call audit run({scope}) after boot and before surface; preset
selection cannot fall back to global readiness. Phase 2 owns that consumer,
source JSON parsing, native DEFERRED retry and one effective merged payload.
Acceptance/move and required commit gates accompany this implementation.
