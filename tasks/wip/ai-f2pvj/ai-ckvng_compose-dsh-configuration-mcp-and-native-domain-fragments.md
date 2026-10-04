---
id: ai-ckvng
kind: subtask
status: wip
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

- [ ] dsh.fragment.json is a domain-root JSON native patch array; existing dependency ordering and source-relative plugin/resource bindings are retained.
- [ ] The exported native composition APIs inspect profile/home/CLI ordering without invoking dump-config or writing user profile files; Python does not evaluate YAML/!!js.
- [ ] MCP stdio/streamable-http preserve serverName, cwd/args/env/headers; unsupported SSE/prompt semantics and unprovable dynamic conflicts are diagnosed.
- [ ] Global then project produces one managed logical name; user-row collisions stop activation; adding/removing one domain preserves other contributions.
- [ ] Environment collection preserves explicit process env precedence and rejects reserved DSH bootstrap variables.
- [ ] Source/generator/contribution drift, full-config replacement and expression/conflict refusal are covered by the new tests.

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
