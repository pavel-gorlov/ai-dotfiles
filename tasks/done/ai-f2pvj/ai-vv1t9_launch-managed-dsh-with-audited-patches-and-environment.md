---
id: ai-vv1t9
kind: subtask
status: done
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_launch.py
- src/ai_dotfiles/commands/dsh.py
- src/ai_dotfiles/cli.py
- tests/unit/test_dsh_launch.py
- tests/e2e/test_dsh_launch.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 3
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
- at: '2026-10-04T21:53:03+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T21:53:32+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T22:50:12+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Launch managed DSH with audited patches and environment

## Goal

Add the thin click-based ai-dotfiles dsh command and a core launcher for one project's audited native composition. This task owns click command integration and registration.

Size driver: One command/core pair, registration and argv/environment/activation tests.

## Scope and ownership

Mode: write. Phase 2 of approved epic ai-47xpm.
Implement Pre-decided decisions 3, 9, 12, 13, 14; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_launch.py
- src/ai_dotfiles/commands/dsh.py
- src/ai_dotfiles/cli.py
- tests/unit/test_dsh_launch.py
- tests/e2e/test_dsh_launch.py

## Definition of done

- [x] Official executable/package and pinned API compatibility are resolved before readiness; missing runtime/providers and unsupported wrappers have actionable diagnostics.
- [x] Global/current-project patches and environment launch the installed CLI without a shell; explicit user argv/env and native override order are preserved.
- [x] User profiles/home patches/package files are unchanged; readiness failures prevent a false success report.
- [x] One process remains bound to one project's MCP/hooks/agents; updates/project changes require restart and the command states this limitation.
- [x] Exit status propagates correctly and new CLI help matches managed launch semantics.
- [x] Tests cover no-shell argv, environment/bootstrap rules, native helper/audit failure and CLI help/restart notices.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** Prior hooks child commit23610458efe496c22a1631ca3aea7e16f9e8eb99
independently verified: parent99a7e5d, exact6paths, +1900/-53, clean index/tree,
206 unit tests and pinned pre-commit/commit-msg/whitespace exit0; main preserved.
Only this next serial Phase2 launcher owner is queued. Actual same-host
audit-before-ready and original relative profile resource base remain mandatory.

**to_do → wip.** tm ready/tm next select ai-vv1t9, parentai-f2pvj, modewrite,
phase3. One current-model worker receives whole generated context and whole epic/
orchestrator, exactly the five listed files. No concurrent writer/read fan-out.
Native managed-host/audit and relative-profile sentinel proof are required in
isolated fixtures; final all-epic runtime remains with ai-f2bcb/ai-pwjnx.


**Native API review → pre-surface gate.** Worker reads published headless-runner:
its apply starts run immediately, unlike API-gateway's AppReady wait. Merely
creating an AppReady boundary cannot guarantee audit before a headless turn.
The same five-file owner investigates bounded public Cordis EntryTree staging,
original profile base/read-only includes and finite native surface release after
actual scoped audit. No private monkeypatch, new agent loop or generic host
framework. Required native failure evidence: no provider turn or ready/surface
before failed managed-row audit; success releases the actual native surface.
Keep all source/profile/home and relative module/include sentinels unchanged.
This implements approved decisions 3/12/14; no new owner choice is introduced.


**Catalog collection → local producer integration hold.** dsh_migrate,
dsh_local_registry and dsh_reconcile are later serial owners. Never read merged
.claude/settings.json as an original catalog source or invent their future
registry schema. Launcher may expose concrete typed local plan/source inputs;
final local activation requires the actual migration producer to be wired and
tested after it exists. Until then, an existing unprovable local registry must
refuse activation with a precise diagnostic, not silently drop contributions.
Worker returns a minimal integration point; coordinator budgets any necessary
bounded continuation under strict five-file ownership. Whole-epic local launcher
acceptance remains open. Project settings.local/.mcp and original storage/global
settings can be collected directly under their existing source contracts.


**Mixed instruction probe → no-broadening activation guard.** Coordinator
/private/tmp/dsh-shared-native-root-probe.py exits0 with actual RC2 public
loadBaselineInstructions: source paths ["**/*.py"] plus always_on:true remains
Codex ALWAYS_ON under incumbent policy, mixed plan has contributors {CODEX},
and DSH emits no block/literal; nevertheless the native provider loads the
shared root AGENTS.md body unconditionally in a non-Python workspace.
Contributor-only unit assertions do not prove effective native exclusion.
Same five-file launcher owner must diagnose the original source/paths and refuse
this unrepresentable managed activation when the effective instruction provider
loads the target-only owned block. Preserve Codex/user bytes and incumbent
classification; no guessed filter/provider or broadening. Check actual disabled/
custom native candidate configuration rather than blanket unsafe assertions.
This enforces existing decisions 6/10/12; no new scope/owner choice.


**Initial launcher review → argv/discovery guards.** Coordinator reads the
whole initial core474/command draft. subprocess Node -e lacks a -- separator
before application argv; actual node -e ... --port exits9 (bad option). Preserve
native app flags with an explicit interpreter delimiter and real argv evidence.
Disabled DSH scopes are skipped, leaving earlier owned global skills/blocks
ambiently discoverable during project-only launch. Read-only retirement guards
must cover disabled scopes too; never materialize their disabled output or
remove foreign user skills. Same five-file owner, all acceptance stays open.


**Initial own gate → selected-scope and instruction checks.** Worker reports
32/32 own cases pass: actual events ready -> nestedinclude -> providerturn,
relative resources correct, broken managed domain no ready/proof/turn, immutable
profile/home bytes. Node argv delimiter and disabled-scope ambient retirement
are corrected. Published agent-loop is a lazy core factory, not an eager surface;
keep that service before audit and stage only eager config.agents. Effective
instruction guard is being tested through live Fiber.config and public native
discovery, including disabled/custom candidates and known nested owned blocks.
Stock preset/scoped success/failure gates are still pending; no ticks yet.


**Effective guard review → scoped provider lookup.** selectedEntries proves
chosen native tree, but draft validateBeforeRelease still fetches root llm and
agentDefaultModel. A valid global provider can hide an absent chosen preset
route. Resolve actual selected services through public agentPresets.serviceFor
and prove global-valid/chosen-missing-provider fails before ready/turn. Same
five-file owner; no synthetic scope or new route policy. Known nested shared
blocks are now checked at their own directories using effective candidates.


**Stock preset probe → immutable HMR/release correction.** Actual RC2 stock
probe observes dsh-hmr.watchConfig reconcileProfilePatches after AppReady,
replacing owned immutable child entries (include:ai-dotfiles-host:hmr becomes
include:hmr). Same five-file owner enforces approved restart-only decision14
for this exact official HMR path with a precise diagnostic. No custom wrapper
rewrite. Public Entry.update releases only staged surface/eager-agent rows;
do not force-replay all core services. Prove live entry identity/tree ownership
and source/profile/home bytes survive readiness; known managed HMR rows require
correct readiness or a specific incompatibility reason, not deliberate disabled
status presented as a source failure. All acceptance remains pending.


**Stock host probe → actual consumer scope.** Published HMR schema has no
watchConfig switch; disabling its root watchers does not stop profile watchers.
Known official HMR is disabled with restart diagnostics, no custom wrapper edit.
Selective public Entry.update now avoids replacing the owned immutable tree.
Worker also observes RC2 headless.run does not mount the selected preset: its
actual Agent remains global. A separately mounted audit preset cannot validate
that consumer. If managed rows target a preset while effective headless consumes
global composition, refuse before ready/turn with a precise unsupported-wrapper/
COMPOSITION_NOT_SELECTED diagnostic. Keep real global headless success/failure.
Real stock Web's public sessionController.create/prompt is the preset-aware
consumer proof; no new loop/factory or cloned preset. Exact limits go to docs.

**Review → acceptance transaction.** Frozen exact five-file diff inspected;
worker final relevant gate871/871 (22.12s), including47 own cases, exits0.
Coordinator independently repeats47/47 (9.11s), mypy84, Ruff5, Black5,
embedded Node syntax and whitespace, all exit0; five source SHA values match.
Real global headless emits ready/include/agent/turn with verbatim argv and
explicit environment; actual stock standard Web opens a loopback HTTP surface,
public SessionController creates the selected Agent, executes a fake-provider
turn and propagates native exit23. Required-row/selected-provider failures
release no ready/surface/turn; scoped audit creates no durable user session.
Original profile/home/relative module/include bytes survive; HMR cannot replace
the owned immutable tree. Active root/nested instruction providers reject an
unrepresentable Codex-only scoped block without changing shared bytes; disabled/
custom candidate configurations pass. Native DEFERRED YAML skill retry and
filesystem-provider readiness are verified. Request JSON is mode0600 and absent
from child argv. Published public Entry.evaluate/disabled/isJsExpr replace the
private disabledOf draft. RC2 headless/preset mismatch and required managed HMR
have precise refusal diagnostics. Local producer integration remains the parent
hold recorded above; this child does not claim completed local activation.

Reproduction: working directory /private/tmp/ai-dotfiles-ai-47xpm;
Poetry prefix uses POETRY_VIRTUALENVS_IN_PROJECT=true, POETRY_CACHE_DIR=
/private/tmp/ai-dotfiles-ai-47xpm-cache/poetry, POETRY_CONFIG_DIR=
/private/tmp/ai-dotfiles-ai-47xpm-cache/poetry-config and native fixture env
_AI_DOTFILES_TEST_DSH_RUNTIME=/private/tmp/dsh-bridge-native-rc2.
Coordinator pytest tests/unit/test_dsh_launch.py tests/e2e/test_dsh_launch.py -q
uses require_escalated only for isolated native loopback; no runtime installation
or production home/network access. Six demonstrated criteria prepared for the
same source/ticks/move/usage/journal commit, then verify before migration.

**wip → done.** tm acceptance6/6 and tm move done exit0. Prepare the exact
five substantive files, this task relocation/usage and orchestrator journal
for one feat(ai-vv1t9) commit. Verify its parent23610458 and clean worktree
before promoting ai-nzmc8. Native named-child and local-producer/launcher join
remain later explicit gates, not acceptance claimed by this child.
