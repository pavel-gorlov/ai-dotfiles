---
id: ai-f2pvj
kind: task
status: wip
created_at: '2026-10-04T11:50:07+00:00'
parent: ai-47xpm
dependencies: []
status_history:
- at: '2026-10-04T11:50:07+00:00'
  status: backlog
- at: '2026-10-04T12:09:42+00:00'
  status: to_do
- at: '2026-10-04T12:27:18+00:00'
  status: wip
---

# Orchestrate DeepSeek Harness target support

## Intake

> support new target dsh(deepSeek harness)

## Context

Approved epic ai-47xpm on 2026-10-04 defines full feasible DSH project/global
support, managed launch, native domain patches and current session model
inheritance. This task is the dispatch contract, not implementation work.
Q1–Q3, impact tags, scope multipliers and size S / M / L are as in the epic;
subtasks use them verbatim.

## What to do

Execute the classification table in its listed order, one write subtask at a
time. Inject the approved epic alongside each subtask's deterministic context.
Give each worker its explicit file ownership; workers are not alone and must
preserve other owners' changes. Commit/acceptance/transitions stay with the
orchestrator, through the applicable git-workflow and taskmanager policies.

Dependency fields use ai-7xrwf as the common layout prerequisite and contain
no chain of three nodes. Remaining producer/consumer prerequisites are explicit
phase barriers and serial order below; never dispatch a later row just because
its common dependency is done. Check prior rows and the current phase barrier
before selecting a task. These milestone barriers avoid unbounded dependency
chains while preserving the approved five-phase delivery sequence.

## Phase order

| Phase | Ordered subtasks | Integration gate |
|---|---|---|
| 0 — contract/ownership | ai-7xrwf → ai-bdfbz → ai-d80em | Typed target/path contract, native roots and shared-block union tests pass. |
| 1 — elements/bridge | ai-86vb3 → ai-bdqha → ai-8n95c → ai-efsr3 | Rendered rows and policy data agree with literal/readiness bridge; safe install and focused native fixture pass. |
| 2 — configuration/launch | ai-ckvng → ai-4m4hj → ai-vv1t9 | Native composition includes one merged hooks/MCP/agent set with origin resources; audited launch and fake-service cases pass. |
| 3 — migration/lifecycle | ai-nzmc8 → ai-m4s7p → ai-k1w43 → ai-gbrqm → ai-b8jes | Local registry/retirement and shared union are integrated before command mutations; project/global CLI and existing lifecycle regressions pass. |
| 4 — acceptance/docs | ai-f2bcb → ai-rr48w → ai-6w1qz → ai-pwjnx | Required native smoke, published references/examples and all final gates pass. |

## Branches and PRs

| Branch | Phases | Cut reason |
|---|---|---|
| epic/ai-47xpm | 0–4 | Final shippable PR at epic close; no mid-plan live step needs merged code. |

One commit per subtask, owned by the orchestrator; workers never commit.
Installed-CLI rehearsals use disposable fixtures within the final PR. This
intake/breakdown creates no implementation branch or PR. Execution starts on
an execution request, as stated in the approved epic.

## Integration points

- Phase 0 exposes concrete layouts and a desired/protected instruction union.
  Every later destructive command path must consume that union before removing
  shared project blocks; existing Codex classification stays unchanged.
- Phase 1 joins renderer payloads, permission data and exact bridge section/tool
  names. No unresolved tool restriction may become an unrestricted agent.
- Phase 2 owns one effective composition. Native rows/resources stay origin-bound;
  required managed ids from all producers enter the runtime audit. Project wins
  for managed names; user conflicts fail rather than rename/overwrite.
- Phase 3 registers local contributions before remove/prune and retires missing
  sources. Command owners integrate the same core collectors, including existing
  Codex prune/remove call sites that could delete DSH-shared project blocks.
- Phase 4 rechecks real native readiness and invocation with isolated fake services.
  Failed gates return to the responsible write owner before epic close. There is
  no parallel write dispatch; the final verification task is read-only.

## Tool ownership

Ownership here means the primary integration responsibility; other tasks consume
that integration and may test/document it without introducing another owner.

| Tool / contract | Primary subtask |
|---|---|
| Concrete target policy/explicit dispatch | ai-bdfbz |
| Official DSH 0.2.0-rc.2 package, filesystem providers and required runtime fixture | ai-f2bcb |
| Native composition APIs, Node helper and standard JSON native fragments/MCP | ai-ckvng |
| Cordis file-URL ESM, system-prompt/tools APIs and Loader readiness bridge | ai-8n95c |
| Python/click CLI command and registration | ai-vv1t9 |
| Rule classification / source-hashed Markdown ownership coordinator | ai-d80em |
| Existing safe symlink/copy primitives | ai-efsr3 |
| Existing domain dependency/runtime/bin machinery | ai-b8jes |
| Poetry, pytest/coverage, mypy, Ruff, Black and pre-commit acceptance | ai-pwjnx |

## Coverage

- Tests: focused suites belong to their write owner; ai-f2bcb owns native runtime
  isolation/fixtures and ai-pwjnx owns all final gate execution/evidence.
- Docs: ai-rr48w owns README, builtin ai-dotfiles skill and the DSH guide;
  ai-6w1qz owns shipped reference templates/native patch example. New command
  and migrate help/completion belong to ai-vv1t9 and ai-gbrqm respectively.
- Process: ai-f2bcb owns test markers/helper packaging; ai-6w1qz owns reference
  templates and ai-pwjnx verifies existing pre-commit gates. New CI/hook/rule
  policy is not needed because the approved required gates use existing checks.

## Subtask classification

| ID | Title | Mode | Size | Executor | Estimate | Context files |
|---|---|---|---|---|---|---|
| ai-7xrwf | Define DSH layout and native target paths | write | M | general-purpose | 0.5–1 d · 5 files · ~+300/−20 LOC | `src/ai_dotfiles/core/paths.py`, `src/ai_dotfiles/core/dsh_layout.py`, `src/ai_dotfiles/core/dsh_targets.py`, `tests/unit/test_dsh_paths.py`, `tests/unit/test_dsh_targets.py` |
| ai-bdfbz | Register DSH target and explicit element dispatch | write | M | general-purpose | 0.5–1 d · 4 files · ~+150/−20 LOC | `src/ai_dotfiles/core/targets.py`, `src/ai_dotfiles/core/elements.py`, `tests/unit/test_targets.py`, `tests/unit/test_elements.py` |
| ai-d80em | Coordinate shared Codex and DSH instruction ownership | write | M | general-purpose | 0.5–1 d · 3 files · ~+250/−30 LOC | `src/ai_dotfiles/core/shared_instructions.py`, `src/ai_dotfiles/core/agents_md.py`, `tests/unit/test_shared_instructions.py` |
| ai-86vb3 | Render DSH skills rules and callable agent payloads | write | M | general-purpose | 1–1.5 d · 2 files · ~+450/−0 LOC | `src/ai_dotfiles/core/dsh_render.py`, `tests/unit/test_dsh_render.py` |
| ai-bdqha | Translate bounded DSH permission policy | write | M | general-purpose | 0.5–1 d · 2 files · ~+250/−0 LOC | `src/ai_dotfiles/core/dsh_permissions.py`, `tests/unit/test_dsh_permissions.py` |
| ai-8n95c | Implement native literal prompt policy and readiness bridge | write | M | general-purpose | 1.5–2.5 d · 4 files · ~+700/−0 LOC | `src/ai_dotfiles/scaffold/templates/dsh_bridge.mjs`, `src/ai_dotfiles/scaffold/templates/dsh_audit.mjs`, `src/ai_dotfiles/core/dsh_audit.py`, `tests/integration/test_dsh_bridge.py` |
| ai-efsr3 | Install DSH elements with copy link and provenance ownership | write | M | general-purpose | 1–1.5 d · 4 files · ~+400/−20 LOC | `src/ai_dotfiles/core/dsh_install.py`, `src/ai_dotfiles/core/fs_copy.py`, `src/ai_dotfiles/core/symlinks.py`, `tests/integration/test_dsh_target.py` |
| ai-ckvng | Compose DSH configuration MCP and native domain fragments | write | M | general-purpose | 1.5–2.5 d · 5 files · ~+700/−0 LOC | `src/ai_dotfiles/core/dsh_config.py`, `src/ai_dotfiles/core/dsh_native.py`, `src/ai_dotfiles/scaffold/templates/dsh_compose.mjs`, `tests/unit/test_dsh_config.py`, `tests/integration/test_dsh_config_drift.py` |
| ai-4m4hj | Translate supported DSH command hooks and resource bindings | write | M | general-purpose | 0.5–1.5 d · 2 files · ~+350/−0 LOC | `src/ai_dotfiles/core/dsh_hooks.py`, `tests/unit/test_dsh_hooks.py` |
| ai-vv1t9 | Launch managed DSH with audited patches and environment | write | M | general-purpose | 1–2 d · 5 files · ~+450/−0 LOC | `src/ai_dotfiles/core/dsh_launch.py`, `src/ai_dotfiles/commands/dsh.py`, `src/ai_dotfiles/cli.py`, `tests/unit/test_dsh_launch.py`, `tests/e2e/test_dsh_launch.py` |
| ai-nzmc8 | Migrate local Claude elements with DSH source registry | write | M | general-purpose | 1–2 d · 5 files · ~+550/−30 LOC | `src/ai_dotfiles/core/dsh_migrate.py`, `src/ai_dotfiles/core/dsh_local_registry.py`, `src/ai_dotfiles/core/local_discovery.py`, `tests/integration/test_dsh_migrate.py`, `tests/integration/test_local_discovery.py` |
| ai-m4s7p | Reconcile DSH drift retired sources and bounded prune | write | M | general-purpose | 1–2 d · 4 files · ~+500/−20 LOC | `src/ai_dotfiles/core/dsh_reconcile.py`, `src/ai_dotfiles/core/gitignore.py`, `tests/integration/test_dsh_reconcile.py`, `tests/integration/test_dsh_prune.py` |
| ai-k1w43 | Wire DSH install add and remove in both scopes | write | M | general-purpose | 1–2 d · 5 files · ~+450/−60 LOC | `src/ai_dotfiles/commands/install.py`, `src/ai_dotfiles/commands/add.py`, `src/ai_dotfiles/commands/remove.py`, `tests/e2e/test_dsh_install.py`, `tests/e2e/test_dsh_global.py` |
| ai-gbrqm | Wire DSH status reconcile and migration CLI | write | M | general-purpose | 0.5–1.5 d · 5 files · ~+300/−40 LOC | `src/ai_dotfiles/commands/status.py`, `src/ai_dotfiles/commands/reconcile.py`, `src/ai_dotfiles/commands/migrate.py`, `src/ai_dotfiles/core/completions.py`, `tests/e2e/test_dsh_migrate.py` |
| ai-b8jes | Wire DSH domain add and remove lifecycle | write | M | general-purpose | 0.5–1 d · 2 files · ~+200/−30 LOC | `src/ai_dotfiles/commands/domain.py`, `tests/e2e/test_dsh_domain.py` |
| ai-f2bcb | Build required isolated pinned DSH runtime acceptance | write | M | general-purpose | 1.5–2.5 d · 3 files · ~+650/−20 LOC | `tests/integration/test_dsh_runtime.py`, `tests/conftest.py`, `pyproject.toml` |
| ai-rr48w | Document DSH lifecycle launcher and compatibility contract | write | S | general-purpose | 0.5–1 d · 3 files · ~+300/−30 LOC | `README.md`, `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`, `docs/dsh-target.md` |
| ai-6w1qz | Sync scaffold references and native fragment example | write | S | general-purpose | 0.25–0.5 d · 3 files · ~+100/−10 LOC | `src/ai_dotfiles/scaffold/templates/global_readme.md`, `src/ai_dotfiles/scaffold/templates/root_readme.md`, `src/ai_dotfiles/scaffold/templates/example_dsh_fragment.json` |
| ai-pwjnx | Verify final DSH epic acceptance and existing regressions | read-only | S | general-purpose | 0.25–0.5 d · 0 files written · ~+30/−0 LOC of gate evidence | `pyproject.toml`, `poetry.lock`, `.pre-commit-config.yaml`, `tests/integration/test_dsh_runtime.py`, `README.md` |

## Planning verification

2026-10-04: the epic is approved at Q3 and its approved plan is unchanged.
Two fresh-context breakdown critic passes completed; the final verdict is
BLOCKING: 0 after explicitly naming the click and Node integration owners.
All 19 subtasks have concrete acceptance, at most five context files and
disjoint write sets. Phase counts are 3 / 4 / 3 / 5 / 4; dependency fields
have no chain of three nodes. tm validate --all and git diff --check pass.
This records planning gates; implementation acceptance below is still pending.

## Execution notes

**Pre-flight → prepared-epic.** The current orchestrate contract requires
subtask parent ai-f2pvj, whereas the previous cut used parent ai-47xpm.
Relinked the existing 19 ids with tm link; scope, acceptance and Q3 approval
are unchanged. Mode detection must use frontmatter across all buckets, not
directory names. No implementation was dispatched during this repair.

**to_do → wip.** Owner invoked orchestrate ai-f2pvj. Execution uses
/private/tmp/ai-dotfiles-ai-47xpm on epic/ai-47xpm, bootstrap b8bfd428.
All 19 child parents are ai-f2pvj. Phase/row order and one writer at a time
are binding. Main baseline: 1104 tests passed, mypy/Ruff/Black clean.
Local Poetry .venv imports worktree src; cache/config live under
/private/tmp/ai-dotfiles-ai-47xpm-cache. Gates: poetry run pytest --cov
(>=80%), required pinned DSH native smoke, mypy src/, ruff check src/ tests/,
black --check src/ tests/, pre-commit run --all-files. Merge remains an
owner action and is excluded from the agent-verifiable goal.

**ai-7xrwf → ai-bdfbz.** Path/layout acceptance is 5/5 after actual diff
inspection and 133 focused/regression tests; mypy74/Ruff/Black clean.
APIs: paths.dsh_home(configured), dsh_absolute_path, find_dsh_project_root;
DshLayout/project_layout/global_layout; DshTargetPlan and project/global
target planners. Native customSkillDirs is list[str]; merge its additions
with effective provider config, never replace unrelated native fields.
Global plan has no cwd/native root; owned_roots bounds scans only and
does not own foreign files. Commit 190b85debc291f4a873f1570f7c765caacd09b52
is verified with pre-commit/commit-msg/whitespace gates; the tree was clean.
The next target-dispatch row is eligible. No native runtime acceptance yet.

**ai-bdfbz → ai-d80em.** Target/path acceptance is 4/4 after actual diff
inspection; 106 focused plus 164 DSH/Codex/path/manifest regressions passed.
mypy74/Ruff/Black/whitespace checks pass. Target.DSH and explicit branches
are available; resolve_target_paths config_root is Path | DshLayout.
DSH agents/description-only unconditional rules contribute to config_path;
shared always-on rules target root_agents_md. Every non-empty source paths
is excluded from DSH activation even when Codex classifies it ALWAYS_ON.
Unknown manifest targets/default/empty lists retain their existing behavior.
Next owner builds the desired/protected project-block union, preserving
Codex classification and both local registries. Commit verification precedes
that dispatch; no native activation has been claimed.

## Acceptance criteria

- [ ] All 19 subtasks are complete with their concrete acceptance gates checked.
- [ ] Every surface in the epic matrix is implemented faithfully or has its explicit native limitation diagnostic; no permission/rule broadening is introduced.
- [ ] Project/global lifecycle, local retirement and mixed Codex/DSH ownership preserve user content; check/dry-run produce zero writes.
- [ ] Required pinned native runtime acceptance passes with real child invocation and audited managed plugin readiness.
- [ ] Full regression/coverage, type, lint, format and required pre-commit gates pass with evidence from ai-pwjnx.
- [ ] README, builtin skill, shipped templates/examples and CLI help match implemented behaviour and matrix boundaries.
- [ ] The final shippable PR is merged under the applicable git workflow and no mid-plan live cut was required.
