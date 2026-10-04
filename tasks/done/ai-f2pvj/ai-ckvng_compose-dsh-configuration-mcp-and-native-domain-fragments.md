---
id: ai-ckvng
kind: subtask
status: done
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_config.py
- src/ai_dotfiles/core/dsh_native.py
- src/ai_dotfiles/scaffold/templates/dsh_compose.mjs
- tests/unit/test_dsh_config.py
- tests/integration/test_dsh_config_drift.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 3
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
- at: '2026-10-04T17:07:17+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T17:07:44+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T21:04:15+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Compose DSH configuration MCP and native domain fragments

## Goal

Collect and validate one effective configuration snapshot using the Node composition helper and native APIs, including named MCP and domain patch contributions. This task owns the Node helper integration.

Size driver: Collectors, one native helper and configuration/ownership tests within five files.

## Scope and ownership

Mode: write. Phase 2 of approved epic ai-47xpm.
Implement Pre-decided decisions 4, 9, 11, 12, 13, 14; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_config.py
- src/ai_dotfiles/core/dsh_native.py
- src/ai_dotfiles/scaffold/templates/dsh_compose.mjs
- tests/unit/test_dsh_config.py
- tests/integration/test_dsh_config_drift.py

## Definition of done

- [x] dsh.fragment.json is a domain-root JSON native patch array; existing dependency ordering and source-relative plugin/resource bindings are retained.
- [x] The exported native composition APIs inspect profile/home/CLI ordering without invoking dump-config or writing user profile files; Python does not evaluate YAML/!!js.
- [x] MCP stdio/streamable-http preserve serverName, cwd/args/env/headers; unsupported SSE/prompt semantics and unprovable dynamic conflicts are diagnosed.
- [x] Global then project produces one managed logical name; user-row collisions stop activation; adding/removing one domain preserves other contributions.
- [x] Environment collection preserves explicit process env precedence and rejects reserved DSH bootstrap variables.
- [x] Source/generator/contribution drift, full-config replacement and expression/conflict refusal are covered by the new tests.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** Phase 1 is complete on epic/ai-47xpm: all seven prior
rows are done, installer commit 4b7b3f9 is verified and full pytest 1652/1652,
mypy79/Ruff/Black163 are green. Queue only this first Phase 2 writer. Its five
context paths own native composition, MCP/env/native fragments and the Node
helper; hook translation and managed launch retain their later owners.

**to_do → wip.** tm ready and tm next select ai-ckvng, parent ai-f2pvj,
mode write, phase null; the approved serial table supplies the Phase 2 hold.
One worker receives the entire tm context, epic and orchestrator with exact
five-file ownership. It must use published native APIs, retry deferred native
frontmatter, preserve source bindings and reject user/dynamic collisions.
Profile inspection is read-only; actual scoped audit before appReady remains
an explicit integration contract with ai-vv1t9, not an offline readiness claim.

**Native research → read-only guard.** The worker found that native
loadProfileDirectory may rewrite package.json when retiring the obsolete
schedule bundle. Inspect and refuse that exact manifest condition before the
native call; preserve profile/home/package bytes and report its origin. This is
technical enforcement of the approved no-profile-writes decision, no repair or
new user-visible choice. Helper inspection and actual scoped audit/commit
boundaries remain distinct; acceptance requires native evidence before use.

**Source handoff → bounded preflight proof.** Existing installer preflight
rechecks source_inventory for source-backed outputs; arbitrary generated JSON
provenance alone does not reread configuration inputs. Domain whole-tree
resources already cover domain fragments. For local settings/config sources,
ai-ckvng may attach bounded raw copies via the existing DshResource and
plan_dsh_install APIs under resources/config-sources/<stable-id>.json, so a
source change after attachment is refused before any write. No installer or
private inventory change is authorized; proof and retirement handoff are pending.

**wip → corrective hold.** The worker is idle with five owned files uncommitted.
Focused native/unit suite: 105 passed, two selected-preset audit failures (107
cases, exit 1); relevant regressions 573/573 and 205/205 pass. mypy81, Ruff/Black
on four Python files, Node syntax and whitespace gates pass. Both failures prove
that the incumbent audit enumerates only root Loader rows, missing loaded rows
in the actual detached PresetTree. Keep all acceptance boxes open and preserve
both failing assertions. Fresh cut review precedes the three-file ai-arqyy
correction; resume this worker only after that correction is accepted/committed.

**corrective hold → wip resume.** ai-arqyy commit
b34cf40d4a06faf13e9d80b4edd52f6eef82d6d4 is independently verified, parent
4b7b3f9, required Git gates exit 0. Only this task's five source files remained
untracked, byte-identical. Audit generator now 2; schema/bridge/policy stay 1.
Coordinator bridge/scoped native gate 51/51 passes. Resume the same five-file
owner with a fresh complete tm context and current contract: finish descendant
domain-include required IDs, shadowed declaration targeted-patch retirement and
unit/integration test placement, then full focused native/regression gates.
Do not weaken the original scoped assertions or declare ready from snapshots;
all six acceptance criteria remain open until final evidence and review.

**Final review → shadowing correction.** Coordinator repeated full focused
115/115 (20.66s), mypy81/Ruff/Black4/Node/whitespace gates exit 0. An additional
real RC2 helper probe finds a remaining declarative loss: global A inserts group
anchor; global B inserts other-domain-client (serverName same); global C inserts
retired-child (same serverName) targeting anchor; project A shadows anchor with
an empty group. Retiring global anchor/C leaves B incorrectly shadowed by the
now-retired child. Actual result contains only anchor/bridge/audit, with
other_domain_retained false. Resolve name precedence over surviving declarations
so another domain reappears when its later shadow retires; add native regression
for insertion anchored to a retired declaration, preserving original sources.
Same five-file owner/scope, no approval or new abstraction; acceptance stays open.

**Namespace probe → final foreign collision gate.** Actual RC2 inspection of
user-client(serverName old), domain insert domain-client(serverName same), then
domain patch user-client(serverName same) returns valid true with both clients
named same. Early user-input collision checks miss this final-state conflict.
Compare effective foreign user rows against surviving native domain declarations
after domain/CLI overrides, including nested includes; preserve exact provenance
and reject id/toolName/serverName conflicts. Same current writer/five-file scope.

**Final namespace gates → selected-domain declaration correction.** Coordinator
full focused 137/137 (57.52s), both independent native probes, mypy81/Ruff/Black4,
Node and whitespace pass. Worker intermediate relevant regression 790/790
(46.40s) passes. One bounded native probe confirms a remaining selected-preset
case: root foreign user-client and a domain-created selected preset's child
domain-client have serverName same, yet inspection returns valid true. Current
domain binding/required-id traversal omits preset descendants. The same five-file
owner must include root plus literal chosen preset descendants with original
locations, retaining unselected-tree exclusion; repeat changed native gates.
This enforces decisions 9/12 and the ai-arqyy selected-tree contract; DoD stays open.

**Final gates → acceptance.** Five-file diff reviewed and writer frozen/idle.
Worker focused native/unit gate 140/140 (18 unit, 122 integration; 14.14s),
relevant 23-file regression 790/790 (8.36s), mypy81/Ruff/Black4/Node/whitespace
all exit 0. Coordinator independently repeated focused 140/140 (11.06s),
Ruff/Black4/Node and earlier mypy81, plus both exact native defect probes.
The original scoped assertions remain unchanged; actual descendant failures,
MCP stdio/loopback HTTP and profile/home/package byte preservation pass.
All six criteria are demonstrated. Native helper remains schema/generator 1;
audit generator 2 retained. MCP environment expansion remains explicitly
MCP_ENV_UNMAPPED; domain/include descendants need literal nonempty IDs, included
user presets are refused when root-index insertion cannot be proved. Snapshots
are drift records, never activation decoders. Launch/audit readiness is still
the following host owner's responsibility; this task proves composition only.

**wip → done.** tm acceptance reports 6/6 checked, exit 0; tm move succeeds
without force and writes tasks/usage/ai-ckvng.json. tm validate reports one
valid file, exit 0. Both coordinator native probes pass again on the final diff,
with source/profile/home/package sentinels unchanged. The Git executor must
commit the five source files, this ticked/moved task, usage and orchestrator
evidence together; hooks dispatch waits for successful commit verification.
