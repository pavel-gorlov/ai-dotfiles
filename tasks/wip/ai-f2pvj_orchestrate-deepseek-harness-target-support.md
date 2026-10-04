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

| Approved milestone / frontmatter phase | Integration gate |
|---|---|
| 0 — contract/ownership / 1 | Typed target/path contract, native roots and shared-block union tests pass. |
| 1 — elements/bridge / 2 | Rendered rows and policy data agree with literal/readiness bridge; safe install and focused native fixture pass. |
| 2 — configuration/launch / 3 | Native composition includes one merged hooks/MCP/agent set with origin resources; audited launch and fake-service cases pass. |
| 3 — migration/lifecycle / 4 | Local registry/retirement and shared union are integrated before command mutations; project/global CLI and existing lifecycle regressions pass. |
| 4 — acceptance/docs / 5 | Required native smoke, published references/examples and all final gates pass. |

Membership and mode are explicit in each child's frontmatter. The classification
table below retains serial row order. During the bounded correction ai-ckvng
may remain wip after its worker returns idle: dispatch ai-arqyy as the sole
writer, accept/commit that correction, then resume ai-ckvng for its scoped gate
before hooks or launch. No overlapping workers or dependency bypass is allowed.

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
  Its Node helper also resolves deferred native skill frontmatter validation:
  valid block/escaped YAML values must use the native parser, never a Python
  placeholder value or permanent STATIC_PARSE_UNSUPPORTED skip. The renderer
  accepts native-parsed metadata/deferred sources; original directories remain
  intact until this validation is integrated. This implements the existing
  valid-native-skill matrix, without adding a Python YAML dependency.
  Native runtime audit is scope-aware: preset-scoped tools/services cannot be
  judged by the global registry view. ai-8n95c exposes an explicit public audit
  boundary for the chosen native agent/scope; ai-ckvng/ai-vv1t9 must resolve the
  effective selection/overrides and await that boundary before reporting ready.
  An unselected composition must not silently fall back to global ready:true.
  Rehearsals must include scoped parent composition and real child inheritance.
  Do not persist a synthetic audit session into user history or repair profiles.
  Native AgentPresetRegistry.mount(ctx, id), acquireScope(id), resolve(id) and
  serviceFor are public in published RC2; preset trees are in-memory and their
  write() is a no-op. Use/prove the public scoped-read/binding path instead of
  fabricating a durable audit session. Native CLI runProfile commits appReady
  after boot, but does not invoke the managed audit boundary: the managed host
  must actually await it before its readiness/surface release, not merely run an
  unrelated offline audit. No complete claim for this consumer exists yet.
  Native loadProfileDirectory can retire an obsolete schedule bundle by writing
  the profile package.json. The read-only helper must inspect and refuse that
  retired manifest case before calling the API, with explicit diagnostics and
  unchanged profile/home/package sentinel evidence. It must not repair profiles.
  ai-ckvng's proposed helper exports separate inspectComposition/parseFrontmatter
  and mountSelectedComposition/auditBeforeReady boundaries; concrete names and
  native scope proof are verified at its acceptance before ai-vv1t9 consumes them.
- Phase 3 registers local contributions before remove/prune and retires missing
  sources. Command owners integrate the same core collectors, including existing
  Codex prune/remove call sites that could delete DSH-shared project blocks.
- Phase 4 rechecks real native readiness and invocation with isolated fake services.
  Before its native gate, ai-wkpk8 completes the recorded fresh local-producer/
  guarded-value collector/launcher join after Phase 3 APIs exist. Its exact five
  files and same collectors retain original guards; no stored snapshot activation.
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

| ID | Title | Size | Executor | Estimate | Context files |
|---|---|---|---|---|---|
| ai-7xrwf | Define DSH layout and native target paths | M | general-purpose | 0.5–1 d · 5 files · ~+300/−20 LOC | `src/ai_dotfiles/core/paths.py`, `src/ai_dotfiles/core/dsh_layout.py`, `src/ai_dotfiles/core/dsh_targets.py`, `tests/unit/test_dsh_paths.py`, `tests/unit/test_dsh_targets.py` |
| ai-bdfbz | Register DSH target and explicit element dispatch | M | general-purpose | 0.5–1 d · 4 files · ~+150/−20 LOC | `src/ai_dotfiles/core/targets.py`, `src/ai_dotfiles/core/elements.py`, `tests/unit/test_targets.py`, `tests/unit/test_elements.py` |
| ai-d80em | Coordinate shared Codex and DSH instruction ownership | M | general-purpose | 0.5–1 d · 4 files · ~+250/−40 LOC | `src/ai_dotfiles/core/shared_instructions.py`, `src/ai_dotfiles/core/agents_md.py`, `src/ai_dotfiles/core/codex_install.py` (only `remove_codex_rule_blocks` delegation), `tests/unit/test_shared_instructions.py` |
| ai-86vb3 | Render DSH skills rules and callable agent payloads | M | general-purpose | 1–1.5 d · 2 files · ~+450/−0 LOC | `src/ai_dotfiles/core/dsh_render.py`, `tests/unit/test_dsh_render.py` |
| ai-bdqha | Translate bounded DSH permission policy | M | general-purpose | 0.5–1 d · 2 files · ~+250/−0 LOC | `src/ai_dotfiles/core/dsh_permissions.py`, `tests/unit/test_dsh_permissions.py` |
| ai-8n95c | Implement native literal prompt policy and readiness bridge | M | general-purpose | 1.5–2.5 d · 4 files · ~+700/−0 LOC | `src/ai_dotfiles/scaffold/templates/dsh_bridge.mjs`, `src/ai_dotfiles/scaffold/templates/dsh_audit.mjs`, `src/ai_dotfiles/core/dsh_audit.py`, `tests/integration/test_dsh_bridge.py` |
| ai-efsr3 | Install DSH elements with copy link and provenance ownership | M | general-purpose | 1–1.5 d · 4 files · ~+400/−20 LOC | `src/ai_dotfiles/core/dsh_install.py`, `src/ai_dotfiles/core/fs_copy.py`, `src/ai_dotfiles/core/symlinks.py`, `tests/integration/test_dsh_target.py` |
| ai-ckvng | Compose DSH configuration MCP and native domain fragments | M | general-purpose | 1.5–2.5 d · 5 files · ~+700/−0 LOC | `src/ai_dotfiles/core/dsh_config.py`, `src/ai_dotfiles/core/dsh_native.py`, `src/ai_dotfiles/scaffold/templates/dsh_compose.mjs`, `tests/unit/test_dsh_config.py`, `tests/integration/test_dsh_config_drift.py` |
| ai-arqyy | Audit selected native preset tree readiness | M | general-purpose | 0.25–0.5 d · 3 files · ~+120/−40 LOC | `src/ai_dotfiles/scaffold/templates/dsh_audit.mjs`, `src/ai_dotfiles/core/dsh_audit.py`, `tests/integration/test_dsh_bridge.py` |
| ai-4m4hj | Translate supported DSH command hooks and resource bindings | M | general-purpose | 0.5–1.5 d · 2 files · ~+350/−0 LOC | `src/ai_dotfiles/core/dsh_hooks.py`, `tests/unit/test_dsh_hooks.py` |
| ai-vv1t9 | Launch managed DSH with audited patches and environment | M | general-purpose | 1–2 d · 5 files · ~+450/−0 LOC | `src/ai_dotfiles/core/dsh_launch.py`, `src/ai_dotfiles/commands/dsh.py`, `src/ai_dotfiles/cli.py`, `tests/unit/test_dsh_launch.py`, `tests/e2e/test_dsh_launch.py` |
| ai-nzmc8 | Migrate local Claude elements with DSH source registry | M | general-purpose | 1–2 d · 5 files · ~+550/−30 LOC | `src/ai_dotfiles/core/dsh_migrate.py`, `src/ai_dotfiles/core/dsh_local_registry.py`, `src/ai_dotfiles/core/local_discovery.py`, `tests/integration/test_dsh_migrate.py`, `tests/integration/test_local_discovery.py` |
| ai-m4s7p | Reconcile DSH drift retired sources and bounded prune | M | general-purpose | 1–2 d · 4 files · ~+500/−20 LOC | `src/ai_dotfiles/core/dsh_reconcile.py`, `src/ai_dotfiles/core/gitignore.py`, `tests/integration/test_dsh_reconcile.py`, `tests/integration/test_dsh_prune.py` |
| ai-k1w43 | Wire DSH install add and remove in both scopes | M | general-purpose | 1–2 d · 5 files · ~+450/−60 LOC | `src/ai_dotfiles/commands/install.py`, `src/ai_dotfiles/commands/add.py`, `src/ai_dotfiles/commands/remove.py`, `tests/e2e/test_dsh_install.py`, `tests/e2e/test_dsh_global.py` |
| ai-gbrqm | Wire DSH status reconcile and migration CLI | M | general-purpose | 0.5–1.5 d · 5 files · ~+300/−40 LOC | `src/ai_dotfiles/commands/status.py`, `src/ai_dotfiles/commands/reconcile.py`, `src/ai_dotfiles/commands/migrate.py`, `src/ai_dotfiles/core/completions.py`, `tests/e2e/test_dsh_migrate.py` |
| ai-b8jes | Wire DSH domain add and remove lifecycle | M | general-purpose | 0.5–1 d · 2 files · ~+200/−30 LOC | `src/ai_dotfiles/commands/domain.py`, `tests/e2e/test_dsh_domain.py` |
| ai-wkpk8 | Join guarded local DSH activation | M | general-purpose | 0.5–1 d · 5 files · ~+300/−60 LOC | `src/ai_dotfiles/core/dsh_config.py`, `src/ai_dotfiles/core/dsh_hooks.py`, `src/ai_dotfiles/core/dsh_launch.py`, `src/ai_dotfiles/core/dsh_migrate.py`, `tests/e2e/test_dsh_launch.py` |
| ai-f2bcb | Build required isolated pinned DSH runtime acceptance | M | general-purpose | 1.5–2.5 d · 3 files · ~+650/−20 LOC | `tests/integration/test_dsh_runtime.py`, `tests/conftest.py`, `pyproject.toml` |
| ai-rr48w | Document DSH lifecycle launcher and compatibility contract | S | general-purpose | 0.5–1 d · 3 files · ~+300/−30 LOC | `README.md`, `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`, `docs/dsh-target.md` |
| ai-6w1qz | Sync scaffold references and native fragment example | S | general-purpose | 0.25–0.5 d · 3 files · ~+100/−10 LOC | `src/ai_dotfiles/scaffold/templates/global_readme.md`, `src/ai_dotfiles/scaffold/templates/root_readme.md`, `src/ai_dotfiles/scaffold/templates/example_dsh_fragment.json` |
| ai-pwjnx | Verify final DSH epic acceptance and existing regressions | S | general-purpose | 0.25–0.5 d · 0 files written · ~+30/−0 LOC of gate evidence | `pyproject.toml`, `poetry.lock`, `.pre-commit-config.yaml`, `tests/integration/test_dsh_runtime.py`, `README.md` |

## Planning verification

2026-10-04: the epic is approved at Q3 and its approved plan is unchanged.
Two fresh-context breakdown critic passes completed; the final verdict is
BLOCKING: 0 after explicitly naming the click and Node integration owners.
All 19 subtasks have concrete acceptance, at most five context files and
disjoint write sets. Phase counts are 3 / 4 / 3 / 5 / 4; dependency fields
have no chain of three nodes. tm validate --all and git diff --check pass.
This records the original planning gates; implementation acceptance below is still pending.

2026-10-04 bounded corrective cut: ai-arqyy isolates the native selected-tree
audit failure found by ai-ckvng's actual RC2 host test. There are now 20 children
(M x17, S x3); the original epic scope and Q3 remain unchanged. This correction
implements the already approved scoped readiness contract rather than adding a
surface or fallback. The current cut-check requires explicit mode/phase fields:
the author now assigns the approved five milestones to positive phases 1–5 and
the recorded modes in every child's frontmatter, including completed children,
without changing their lifecycle or reopening history. Fresh-context corrective
critic checked the epic, this contract and all 20 children: BLOCKING: 0.
Command tm cut-check ai-f2pvj exited 0; stdout was
"+ ai-f2pvj: cut-check passed", stderr empty. tm validate --all exited 0
(48 valid files, 33 legacy done files skipped). Dispatch ai-arqyy may proceed
while ai-ckvng's writer remains idle; the original Q3 scope remains unchanged.

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
that dispatch; commit 2c8c2bcb0bb6f1016f38c55439c257008482d6fd is verified
with clean worktree and pre-commit/commit-msg gates. No native activation
has been claimed.

**ai-d80em → ai-86vb3.** Phase 0 union acceptance is 5/5 after actual
diff inspection, 162 focused plus 78 Codex regressions and full pytest
1249/1249. mypy75/Ruff/Black/whitespace pass. APIs: project_instruction_plan
returns blocks, wanted_blocks, protected_blocks, keep_blocks, removable_names
and dsh_literal_rules. Shared Markdown keys/project_root are canonical;
DshLayout/native discovery stays lexical. Both local registries use
rule_blocks {project-relative AGENTS.md: list[marker-safe names]} and protect
entries independently of empty/disabled catalog targets. Invalid/traversing/
outside-symlink records fail before mutation; sources/bodies are not stored
in this common protection schema. agents_md.remove_rule_blocks preserves
LF/CRLF/unowned whitespace; Codex removal delegates to it. Lifecycle owners
must compute keep union before delete/prune. Codex classification is unchanged,
DSH-only description rules are private bridge sources. Phase 1 renderer is
next after commit verification; native runtime acceptance remains pending.
Commit 79ae642e0f1c30afe02a63233ef928da93880082 is verified; the tree was
clean and required pre-commit/commit-msg gates passed. Phase 0 is complete.

**ai-86vb3 → ai-bdqha.** Renderer acceptance 6/6 after actual source/test
inspection and 411 focused/regression tests (142 renderer cases); mypy76,
Ruff/Black/whitespace clean. DshRenderResult statuses READY/DEFERRED/MANUAL;
activate READY only. validate_skill/render_rule/render_agent retry accepts
native_frontmatter Mapping[str, object], resolved by ai-ckvng's native parser.
DshDiagnostic has code/origin/element/field/reason/blocking;
DshProvenance has source/origin/element/source_sha256/generator and as_dict.
DSH_RENDER_GENERATOR_VERSION=1. native_tool_names and immutable
CLAUDE_TOOL_NAMES are the shared exact map (Read -> read,read_image;
Write/Edit/Glob/Grep/Bash/WebFetch/WebSearch; no Task/Agent/MCP guessing).
Agent row ids ai-dotfiles-agent-<name>, toolName ai_dotfiles_agent_<name>,
provider spawn; persona string is literal. bridge_data retains descriptions,
sourceModel/provenance; no unsupported description key in native Config.
required_tools includes allow AND deny names for audit. Native options retain
partial parent/provider inheritance. Installer must gate shared blocks on
render_rule READY and enumerate source rules for excluded-path diagnostics.
Permission translator is next after commit verification; native runtime
activation/readiness remains pending with ai-8n95c/ai-f2bcb.
Commit 1baa6daf9053932710aa69bc8c4914274f9c8417 is verified; the tree was
clean and required pre-commit/commit-msg gates passed.

**ai-bdqha → ai-8n95c.** Permission translator acceptance is 4/4 after
complete diff inspection and 385 focused/regression tests, including 146
permission cases; mypy77/Ruff/Black/whitespace pass. APIs:
translate_permissions(permissions, provenance=...) -> DshPermissionPolicy;
merge_permission_policies retains source order/repeats/origins. Exact mapped
deny/ask views and required_tools are sorted/deduplicated. bridge_data schema
version 1 and generator 1 supplies deny/ask/requiredTools/blocked/contributions/
diagnostics; raw malformed values have independent snapshots. Unknown fields,
malformed data and unsupported deny/ask block policy activation; allow-only
gaps stay nonblocking and grant nothing. Consumers must translate original
sources before settings merge, reject unknown schema/blocked/malformed payloads
and JSON parse errors, never replace restrictions with empty policy or presets.
The next owner implements actual monotonic deny, preserving ask waterfall,
literal prompt/description bridge and readiness on pinned DSH. Native startup
audit ignores absent/disabled required ids, so explicitly assert every managed
id and mapped tool after Loader settlement. Commit verification precedes
dispatch; native runtime acceptance has not yet been performed.
Commit 79c9d8c9b5800dfcdc79d254b1bdca8cd0f76f6b is verified with
clean tree and required pre-commit/commit-msg/whitespace gates.

**Pre-existing → bounded DSH ownership.** pre-existing, do not fix in
this branch: safe_symlink/copy_tree_into and the existing Codex skill
materialization paths can replace existing destinations; those incumbent
policies are outside the DSH charter. DSH installer must perform its own
ownership/collision/parent-symlink preflight before invoking shared primitives.
Do not widen ai-efsr3 into Claude/Codex cleanup or change existing default
filesystem semantics. fs_copy.py already exists and preserves executable bits.

**ai-8n95c → ai-efsr3.** Bridge acceptance is 6/6 after actual four-file
review and coordinator native pytest 37/37. Worker final combined pytest
596/596 (37 focused, including 36 real runtime tests; 559 regressions),
mypy78/Ruff/Black2/both node --check/whitespace pass. Exact RC2 installation
/private/tmp/dsh-bridge-native-rc2 and actual CLI --version are verified;
test homes/profiles/cache/fake services are isolated. Reuse test-only
_AI_DOTFILES_TEST_DSH_RUNTIME for disposable setup; never install at runtime.
APIs: build_bridge_config(agents, literal_rules, permissions=...) accepts
READY/unblocked only; agent metadata extends bridge_data with rowId,
requiredTools, deep-copied exact toolFilter/agentOptions (null != empty allow).
bridge_audit_requirements adds each producer's required ids/tools/services/
subagent providers. Schema/generators all 1; bridge/audit row ids
ai-dotfiles-bridge/ai-dotfiles-audit. bridge_module_text/audit_module_text
prepend managed signature, template source SHA and generator; read errors
are ConfigError. Installer must materialize these owned module/resources
with provenance; aggregate config remains the Phase 2 collector's concern.
Native ctx.aiDotfilesAudit.run({scope}) / auditReady(ctx, config, {scope})
is awaited AFTER Loader boot, BEFORE surface. apply is synchronous to avoid
self-deadlock. Unique configured leaf ids or qualified Entry.id are allowed,
ambiguous leaves fail; root Include prefixes include:. Preset profiles without
chosen native scope return COMPOSITION_NOT_SELECTED/pending, not ready.
Actual parent-preset scoped tools/services and stock spawn inheritance pass;
no synthetic durable user audit session is allowed. Only managed required-row
failures are fatal; foreign optional failures remain diagnostics. Exact native
filter/options and final prompt sections are verified; no unrestricted child,
complete-persona repair or ask/sandbox bypass. Native bridge gate is proven;
full launcher/runtime acceptance remains Phase 2/4. Commit verification precedes
the next installer dispatch and Phase 1 closes only after that row's gate.
Commit f7fb93f84dfe392a0a4237b53c65a739f27835a8 is verified; tree was
clean and required pre-commit/commit-msg/whitespace gates passed. Pinned
Black added two accepted trailing commas in test parameter lists only.

**ai-efsr3 → ai-ckvng.** Installer acceptance 5/5 after actual three-file
diff review. 78 installer cases include four published native skill-provider
project/global x link/copy cases; combined 941/941, corrected bridge-first
115/115 and worker full 1652/1652 pass. Coordinator full pytest 1652/1652
(8.86s), mypy79/Ruff all/Black163 all pass. Initial full run found four fixture
setup errors masked by target-first ordering; owned test now explicitly imports
and exposes bridge_native_runtime, without pytest_plugins or skips. Phase 4
may consolidate this required fixture across bridge/target/runtime tests.
APIs: collect_dsh_elements -> DshInstallPlan; plan_dsh_install accepts retried
READY metadata/results, permissions, DshResource; preflight_dsh_install checks
all output/registry/shared paths, source snapshots and fresh local protection
before writes; apply_dsh_install -> DshInstallResult. read_dsh_inventory,
verify_dsh_owned_output, output_drift, audit_path are public read-only helpers.
DshOutput can represent generated content or source link/copy; DshResource binds
safe relative paths under resources_dir. Schema/install generator both 1.
records keyed relative to dsh_dir carry mode/source/source_inventory/
output_inventory/source_tree_sha256/provenance/generators; source_records retain
READY/DEFERRED/MANUAL raw source and diagnostics, rule_blocks is the shared
protection shape. Domain resource provenance uses the complete tree digest.
Catalog resources are copied under resources/domains/<domain>, independent of
Claude; bridge/audit source/generated signatures remain intact. Native skill
bundles stay whole, no Codex description transformation. New optional
safe_symlink chmod_scripts=True preserves incumbent behavior; DSH passes False.
Foreign/modified entries are refused; outer aliases preserve native lexical
paths while managed symlink parents are rejected. fs_copy.py unchanged.
Aggregate config.json/patch.json/hooks.json remain ai-ckvng/ai-4m4hj's concern.
native_rows must be merged across scopes before inserting one bridge/audit set.
desired_output_keys/current_source_ids and result.retired_output_keys identify
previous READY native outputs absent from the current desired set. Omission
alone cannot prevent discovery of an old linked skill; later reconcile/launcher
must retire it or refuse stale activation after catalog/local union. Shared
block retirement likewise waits for the desired/protected union. Do not claim
safe activation from file presence or preserve an old unsupported restriction
as an unrestricted native element. Phase 1 gate is green; commit verification
precedes Phase 2 dispatch. Whole launcher/runtime acceptance remains pending.
Commit 4b7b3f9a6b98b1d93d416a5cc270819a825c7714 is verified with a clean
tree on epic/ai-47xpm and pre-commit/commit-msg/whitespace gates. The same
transaction includes the standard file-mode tm usage snapshot; source ownership
is unchanged. Phase 2 may now dispatch its first ordered writer ai-ckvng.

**ai-ckvng → ai-arqyy.** ai-ckvng is held in wip with its writer idle:
105/107 focused cases pass, two actual selected-preset readiness cases expose
the existing root-only audit enumeration bug. Regressions 573/573 and 205/205,
mypy81/Ruff/Black/Node checks pass. The bounded corrective cut has 20 children;
tm cut-check and tm validate --all pass. Run a fresh-context cut critic before
the sole three-file ai-arqyy writer. That writer must union actual selected-tree
and root entries, retain strict required-row/body/filter/options checks, and
bump audit template/Python generator together. Never fake Loader/session state.
After its verified commit, resume ai-ckvng's scoped gates before hooks/launch.

**ai-arqyy → ai-ckvng.** Corrective audit acceptance is 4/4 after real three-file
review. Worker 415/415 native/render/policy/installer and 67/67 config/scoped
regressions pass; coordinator bridge plus both original selected-scope failures
now pass 51/51. mypy81/Ruff/Black2/Node/whitespace gates exit 0. Audit generator
2 is synchronized across Python/ESM and installer metadata; schema/bridge/policy
remain 1. Both auditReady(rootCtx, config, {scope}) and scoped run use the actual
selected service's public Impl/Fiber/Entry tree and settled root union, Entry
identity deduplication, and fatal SCOPED_TREE_UNAVAILABLE if proof is absent.
Exact persona/filter/options and optional-foreign diagnostics remain intact;
real child composition/model inheritance and no audit-session history pass.
The corrective commit must include this cut's mode/phase authoring, new child
ticks/move/usage and current held ai-ckvng journal, but exclude its five source
files. After commit verification, resume that five-file owner for descendant
domain-include readiness, shadowed targeted-patch retirement, test layout and
full focused native gates. Hooks/launch remain held until ai-ckvng is accepted.
Corrective commit b34cf40d4a06faf13e9d80b4edd52f6eef82d6d4 is independently
verified against parent 4b7b3f9 with exact 26-path allowlist, clean index and
only the five held config files untracked; main HEAD/status preserved. Required
pre-commit/commit-msg/whitespace gates exit 0 with no formatter mutations.
The same ai-ckvng writer may now resume with refreshed complete context.

**Published host API → launcher hold.** Read exact installed RC2
@deepseek-ai/dsh/lib/profile-boot-BZ2ZjNWi.js and app-boot/lib/index.js.
Native runProfile commits its private AppReady after boot without managed audit;
an unrelated preflight process does not enforce our same-host readiness gate.
Public boot(binName, absoluteConfigPath, patches, prepare, bareModuleBaseUrl)
and provideCmdline are available, but root Include resolves relative modules
beside absoluteConfigPath. ai-vv1t9 must preserve the original profile base for
user relative modules/includes when hosting an owned config, with actual native
sentinel/relative-path evidence. Do not call mutating prepareProfile/runProfile
as a substitute for that gate or write a cordis.yml into the user profile.
This is technical enforcement of decisions 3/12/14, no new surface or choice.

**ai-ckvng review → survivor precedence correction.** Worker focused115/115 and
regressions790/790 pass; coordinator repeated focused115/115 and style/type gates.
Actual additional RC2 probe shows another-domain row remains shadowed after its
later competing declaration is itself retired with a shadowed insertion anchor.
Keep ai-ckvng wip and its six criteria open; resume the same five-file owner for
bounded surviving-declaration precedence and native regression. Hooks/launch
remain held. This is the approved contribution preservation contract, not a fork.
Another actual RC2 probe confirms a final user/domain collision missed by early
input checks: domain patch changes user-client serverName to the inserted native
domain-client's name, and inspection incorrectly returns valid true. The same
writer must reject effective foreign id/tool/server conflicts after domain/CLI
overrides, with precise origins. This implements existing decision 9 only.

**ai-ckvng final gate → selected-domain declaration correction.** Root focused
137/137 and both exact native probes pass; worker relevant regression 790/790
passes on the intermediate diff. A bounded actual native probe then confirms
selected native-domain preset children are omitted from domain ownership and
required-id collection: foreign root client and selected domain child share a
serverName but valid remains true. Same five-file owner now collects root plus
literal chosen preset descendants, retaining exact source fields and excluding
unselected tree descendants. This is existing namespace/readiness scope; no new
user choice. Hold acceptance/hooks until updated native/static gates and commit.

**ai-ckvng review → acceptance transaction.** Frozen five-file diff has worker
140/140 focused native/unit and 790/790 relevant regressions, all required
type/style/syntax/whitespace gates exit 0. Coordinator independently repeats
140/140 (11.06s), both exact native defect probes and static gates. Original
scoped assertions remain intact. Six composition criteria are demonstrated;
prepare tick/move/usage/source changes in one subtask commit before hooks.
Consumer APIs: DshConfigSource / DshNativeContribution (hooks must provide ONE
combined contribution), collect_dsh_config_sources / collect_dsh_configuration,
compose_dsh_configuration, attach_dsh_config_outputs, inspect_dsh_configuration;
read_dsh_config_snapshot and dsh_config_drift are read-only drift operations.
Fresh sources always drive activation; attach uses guarded raw-source resources.
Native helper inspect is read-only and not readiness: actual managed host must
mountSelectedComposition and await auditBeforeReady before its readiness commit.
Domain required IDs cover root plus chosen preset/includes only. Hooks/launcher
retain their original owners and remaining full runtime acceptance is open.

**ai-ckvng acceptance → done transaction.** tm acceptance 6/6, tm move done
and tm validate all exit 0; task and usage paths are prepared with five source
files and this journal for one feat(ai-ckvng) commit. Exact independent native
probes repeat exit 0 after the final selected-preset correction. The writer is
idle; verify the Git commit before promoting ai-4m4hj. No runtime/CLI readiness
or whole-epic completion is claimed by this composition gate.

**ai-ckvng → ai-4m4hj.** Commit
99a7e5daa7415756601f62003a680b7b929c1c34 independently verified: parent b34cf40,
8 changes/9 paths, +4980/-7; source/acceptance/task move/usage/journal together.
Pre-commit, commit-msg and whitespace exit 0, no formatter changes. Index and
worktree clean, main unchanged. Promote only this next serial two-file hooks
owner. Its collector must preserve all original global/domain/project handlers
in ONE combined DshNativeContribution; otherwise scope precedence would discard
global handlers. Use DshOutput/DshResource and copied domain resources with source
preflight, never depend on a Claude installation. Read-only published native
hook parser/protocol evidence complements pure mocked unit tests; actual host
readiness and required final runtime fixture remain with later owners.

**ai-4m4hj initial collector → bounded resource correction.** Reviewed draft
always inventories/copies source.path.parent, even an empty hook map; implicit
global/local settings must not sweep ~/.claude or a repository. Preserve guarded
raw inputs and known handler/support roots only, while explicit bounded catalog
domain resources retain their whole-tree discipline. Same two-file writer;
required unit/native gates stay open. This implements existing bounded ownership,
not a scope fork. Official native Claude matcher uses exact word/pipe alternatives,
so read|read_image translation does not need an invented regex workaround.


**ai-4m4hj review → acceptance transaction.** All five hook criteria are
backed by worker 206/206 and full combined 830/830, coordinator 206/206 and
actual seven-event/two-origin native probe, mypy82/Ruff/Black2/whitespace exit 0.
No skip or protocol emulation. Original raw sources and bounded referenced
hook resources carry guarded source/tree provenance; never copy implicit
~/.claude/project parents wholesale. One combined DshNativeContribution named
hooks avoids scope precedence dropping global handlers. Native compatibility
limits are explicit; internal required_semantics evidence blocks unsupported
required behaviour without a new source format or flag. Initial loopback
sandbox refusal was resolved by repeating the entire unchanged gate in isolated
fixtures. Final comment-only docstring correction matches resource policy.
Prepare task ticks/move/usage/source and journal in one feat(ai-4m4hj) commit;
verify commit before launcher promotion. Same-host readiness, relative user
profile origins and actual named-child acceptance remain open with later owners.


**ai-4m4hj acceptance → done transaction.** tm acceptance 5/5 and tm move
done exit 0. Two source/test additions plus ticks/task relocation/usage and this
journal form one commit; verify exact paths, parent 99a7e5d and clean tree before
promoting ai-vv1t9. Native host readiness remains its explicit next concern.

**ai-4m4hj Git gate → pinned formatting.** Black25.1 adds twelve trailing
commas to test function parameters only; actual twelve-hunk diff accepted,
core unchanged. Git owner repeats206 hook unit tests and required Git gates
before the same subtask commit. No extra source change or weakened native gate.


**ai-4m4hj → ai-vv1t9.** Hooks commit23610458efe496c22a1631ca3aea7e16f9e8eb99
independently verified against parent99a7e5d: exact6paths, +1900/-53; source,
ticks/task relocation/usage and notes together. Core SHA unchanged; only twelve
accepted Black25.1 test commas, repeated206/206 and all Git gates exit0. Index/
worktree clean, main unchanged. Promote only the five-file managed-launch owner.
It consumes collect_dsh_hooks/attach_dsh_hook_outputs and ONE hooks contribution,
current raw configuration/native rendering, source guards and selected-tree audit.
A stale retired native-discovered output must be retired or refused, never treated
as harmless omission. Official RC2 runtime is resolved, not installed; Python
subprocess uses shell=False and explicit argv/environment/status propagation.
Actual host boot must preserve user profile relative module/include origin and
await auditBeforeReady with actual chosen scope before readiness/surface. Do not
use mutating runProfile/prepareProfile or an unrelated offline audit as readiness.


**ai-vv1t9 native API review → pre-surface gate.** Published headless-runner
starts its run during apply instead of waiting for AppReady; audit must precede
that surface too. Same five-file owner investigates public Cordis EntryTree
staging with original profile base and read-only native includes; audit actual
selected scope, then release finite supported native surfaces. Real failure
probe must show zero provider turn/exposure before failed managed-row audit;
success must use actual native surface/exit. Preserve argv/overrides and profile/
home/relative module/include bytes. No private monkeypatch or generic new host;
unprovable wrappers remain explicit diagnostics. Existing decisions 3/12/14.


**ai-vv1t9 catalog collection → local producer integration hold.** Later
ai-nzmc8/ai-m4s7p provide migration/registry/reconciliation. Launcher must not
guess that schema or mistake merged .claude/settings.json for raw catalog input.
Concrete typed local inputs may be exposed now, but actual producer/launcher
join and tests remain mandatory before final acceptance. Existing unprovable
local registry refuses activation, never silently omitted. Coordinator must
assign a bounded continuation if the actual join needs launcher writes outside
the later owner's current five-file set; no dormant feature flag or new scope.


**ai-vv1t9 mixed instruction probe → no-broadening guard.** Actual RC2
loadBaselineInstructions loads a shared Codex-only paths:["**/*.py"] /
always_on:true root block unconditionally; probe
/private/tmp/dsh-shared-native-root-probe.py exits0, nativeBodyPresent:true.
Foundation contributor sets correctly exclude DSH but cannot filter a physical
shared AGENTS.md for native discovery. Same launcher owner must stop that
unrepresentable effective activation with precise source/field diagnostic,
preserve Codex/user bytes and existing classifier, and inspect actual native
provider/candidate configuration. No custom filtering runtime or source rewrite.
This is the approved no-rule-broadening boundary, not an independent feature.


**ai-vv1t9 draft review → argv/discovery guards.** Entire initial474-line
core/command reviewed. Actual Node probe confirms app --port becomes a Node
flag without -- (exit9); native argv needs an interpreter delimiter. Previously
owned global native-discovered outputs must be refused/retired even when global
manifest no longer enables DSH. Same owner adds read-only disabled-scope guards,
preserves foreign files and proves argv. Native/acceptance gates remain open.


**ai-vv1t9 initial32 gate → scoped/instruction proof.** Worker own32/32
pass with real ready -> nestedinclude -> providerturn, failed required domain
no ready/turn and profile/home bytes unchanged. Delimiter and disabled-scope
retirement fixed. Native agent-loop stays as lazy core factory; eager config.agents
is staged. Effective native instruction guard and real stock preset/scoped
success/failure tests remain pending, all six launcher criteria still open.


**ai-vv1t9 guard review → selected provider lookup.** Live selected-tree
enumeration is present; draft root llm/default-model lookup still misses a
preset-scoped provider route. Same writer resolves actual selected services via
public serviceFor and adds global-valid/chosen-missing failure-before-turn
proof. Launcher acceptance remains open until full final native/static gates.


**ai-vv1t9 stock probe → immutable HMR/release correction.** RC2 HMR after
AppReady replaces include:ai-dotfiles-host:hmr with include:hmr through public
reconcileProfilePatches. Same owner blocks known official live recomposition
under already approved restart-only decision14, emits precise diagnostics and
releases only staged rows via public Entry.update. Preserve source/profile/home
bytes and actual selected-tree ownership; do not replay all services or rewrite
arbitrary wrappers. Final native/static gate and all six criteria stay open.


**ai-vv1t9 native consumer review → scope fidelity.** RC2 HMR has no
watchConfig:false; only the known official live path is disabled with restart
diagnostics. Stock headless Agent remains global even with a separately mounted
audit preset. Refuse preset-managed/global-headless mismatch before ready/turn,
never label that separate scope as consumer readiness. Global headless remains
supported; real stock Web sessionController create/prompt must prove preset-aware
consumer readiness. Same five-file owner, original profile bytes preserved.

**ai-vv1t9 review → acceptance transaction.** Frozen five-file launcher inspected;
worker relevant native/regression871/871 and coordinator own47/47 pass. Root
mypy84/Ruff5/Black5/embedded Node syntax/whitespace exit0; SHA values match.
Actual global headless and actual standard-preset Web SessionController prove
audit-before-ready/turn, argv/env/profile-relative resources and exit propagation.
Required-row/scoped-provider failures release no ready/surface/turn. Original
profile/home bytes stay intact; public EntryTree/Entry.update staging preserves
immutable owned tree, official HMR is disabled with restart diagnostics. Public
Entry.evaluate/disabled/isJsExpr used, no private disabledOf or synthetic audit
session. Active root/nested providers refuse unrepresentable shared Codex scoped
blocks; disabled/custom candidates pass; native DEFERRED skills/provider checks
pass. Private request file is mode0600 and credentials are absent from argv.
RC2 headless with preset refuses COMPOSITION_NOT_SELECTED; docs owner must state
this and HMR limits. Prepare six ticks/move/usage in one launcher commit. Local
registry activation remains an explicit parent hold: after migration/reconcile
producer APIs exist, budget the bounded launcher join before final native gates.
Do not invent registry schemas or activate serialized config.json. Next serial
owner ai-nzmc8 supplies fresh originals/provenance and per-layout merge contract.

**ai-vv1t9 acceptance → done transaction.** tm acceptance6/6 and move done
exit0; source/ticks/task relocation/usage/current journal are prepared together.
Verify one feat(ai-vv1t9) commit against parent23610458 before migration; no
extra source writes or publication. The global/catalog launcher gate is proven,
while named-child final acceptance and local producer activation remain open.

**ai-vv1t9 → ai-nzmc8.** Commit1976ead5271a776837f105be04c9c0b5fcf2b7ed
independently verified: parent23610458, exact9paths +2511/-60, ticks/move/usage
and source together. Pinned pre-commit/commit-msg/whitespace exit0, no formatter
mutations; worktree/index clean and main baseline unchanged. Phase3 gate passes.
Promote only five-file Phase4 migration owner; local discovery must exclude both
catalog domain symlinks and copy-ownership entries, preserve original raw settings/
MCP/hooks, classify gaps and expose guarded current producer inputs for later
reconciliation and launcher join. Never activate stored aggregate snapshots.
No local-producer join may silently omit or duplicate one layout's render plan.
The bounded launcher continuation remains a required later acceptance hold.

**ai-nzmc8 to_do → wip.** tm ready/next confirm parentai-f2pvj, modewrite,
phase4. The sole current-model worker reads full generated434-line context,
whole epic/orchestrator and applicable instructions; exact five-file ownership.
Fresh typed local-original producer, shared protection registry, copy exclusion
and zero-write dry-run are the gate. No concurrent writer/read fan-out; original
launcher join remains held for its bounded continuation after concrete APIs.

**ai-nzmc8 producer review → guarded-value integration hold.** Root/worker
confirm public DshConfigSource and DshHookSource are path-only; owned settings/
MCP need a fresh guarded user-only projection to avoid catalog duplication.
Same five-file migration owner supplies typed original path/hash/value/ledger
guards and an explicit temporary REFACTOR boundary diagnostic. No snapshots,
private API or guessed flags. The already required bounded local-launcher join
must also adapt these two public collectors and complete projected migration
classification/activation. Budget at most five files in a Phase5 continuation
before required native acceptance; keep Phase4's five concerns and Q3 unchanged.
This is necessary existing full-feasible local delivery, not a new user fork.

**ai-nzmc8 original ledger review → ambiguous fields.** Existing settings
ownership proves permission/hook contributions only; env/scalar origin is absent.
Producer retains originals/ledger guards and explicit unproven_fields; later join
must diagnose unresolved original provenance and never infer it by catalog-value
equality. Supported tracked projections/MCP server ownership remain eligible.
Keep this genuine source-provenance limitation distinct from the guarded-value
API continuation, which still must implement supported local activation.

**Documentation recheck → pinned release retained.** 2026-10-04T23:03Z:
current official apps/cli/README.md read through web; its native layer order is
bundles/profile/home/CLI and changes without HMR apply on restart. Public npm
view dist-tags exit0 with credentials/config disabled and temporary-only cache:
latest=0.2.0-rc.2, next=0.2.0-rc.2, alpha=0.2.1-alpha.1. Initial sandbox DNS
failure resolved with read-only public-registry escalation, no package install.
Delivery remains approved RC2; preview docs are not treated as shipped runtime.

**ai-nzmc8 producer → lifecycle hand-off.** Concrete DshLocalInputs boundary
returns one catalog/local install and fresh original/projection/ledger guards.
plan_dsh_migration composes supplied original catalog/global sources once.
Recorded catalog inventory without fresh catalog_plan refuses, preserving other
contributors. Next ai-m4s7p must support verified own local-rule refresh through
an in-memory union plan, preserving Codex/user protection; no temporary registry
deletion. Report any actual public-installer gap before adding owned files.
The guarded-value/launcher continuation remains before Phase5 native acceptance.

**Local activation hold → ai-wkpk8 bounded cut.** tm create allocates the
single five-file continuation, after Phase4 lifecycle and before Phase5 native
acceptance. It joins actual fresh local originals/projections/ledger guards with
the same public config/hooks collectors and launcher, one plan per layout, and
completes supported migration classifications. Ambiguous original env remains a
specific source-provenance gap, never guessed; no new user flag/engine/schema.
Cut now has21 children (M x18, S x3), phase concerns3/4/4/5/5. Scope/Q3 unchanged;
whole-cut fresh critic and tm cut-check must pass before continuation dispatch.
No critic read fan-out while the ai-nzmc8 writer is active. Task remains backlog.

**ai-nzmc8 initial74 → original-presence correction.** Own74/native2 and
mypy86 pass on draft. Root actual temp probe creates settings.local.json deny
Bash after raw_sources0 planning; verify accepts stale set. Same sole writer
adds finite raw-source absence/presence proof and fail-before-write tests before
freeze. No new files or changed scope; acceptance/next writer remain held.


**21-child cut → accepted continuation.** Fresh-context critic reads whole epic,
orchestrator and all21 children, checks1–7 with BLOCKING0. Actual tm cut-check
ai-f2pvj exits0, stdout '+ ai-f2pvj: cut-check passed', stderr empty. Coordinator
structural check and tm validate --all also exit0 (49valid/33legacy skipped).
ai-wkpk8 stays backlog until Phase4 completion; original Q3/full-feasible scope
unchanged. No concurrent source writer during critique.

**ai-nzmc8 frozen producer → acceptance proof.** Exact five-file diff reviewed;
worker unchanged22-suite command passes1045/1045 (15.62s), exit0, no skips, with
real published RC2 runtime. Coordinator own80/80 (1.34s), native2, mypy86,
Ruff/Black5 and whitespace all exit0. The initial source-presence defect is
corrected for all four raw JSON originals; stale original/ledger/projection
inputs fail before writes. Strict registry source/output generator provenance,
READY-to-MANUAL custody, copy/domain-link exclusion and zero-write dry-run pass.
Five producer ticks are proven; projected local activation remains ai-wkpk8 and
verified own-rule refresh/retirement remains ai-m4s7p. No stored aggregate is
activated and ambiguous env/scalar origin stays MANUAL with exact fields.

**ai-nzmc8 wip → done.** tm acceptance5/5 and move done exit0; exact five
source files, ticks, relocation, usage and21-child cut metadata prepare one
transaction. Verify against parent1976ead5 before ai-m4s7p promotion; no extra
source writes, publication or concurrent owner.

## Acceptance criteria

- [ ] All 21 subtasks are complete with their concrete acceptance gates checked.
- [ ] Every surface in the epic matrix is implemented faithfully or has its explicit native limitation diagnostic; no permission/rule broadening is introduced.
- [ ] Project/global lifecycle, local retirement and mixed Codex/DSH ownership preserve user content; check/dry-run produce zero writes.
- [ ] Required pinned native runtime acceptance passes with real child invocation and audited managed plugin readiness.
- [ ] Full regression/coverage, type, lint, format and required pre-commit gates pass with evidence from ai-pwjnx.
- [ ] README, builtin skill, shipped templates/examples and CLI help match implemented behaviour and matrix boundaries.
- [ ] The final shippable PR is merged under the applicable git workflow and no mid-plan live cut was required.
