---
id: ai-47xpm
kind: epic
status: backlog
created_at: '2026-10-03T19:50:33+00:00'
success_metrics:
- DSH project and global lifecycle renders all faithfully representable surfaces.
- Installed agents are callable and retain literal instructions and descriptions.
- Managed MCP, hooks, configuration and permissions are activated and audited.
- Local migration and shared Codex/DSH ownership preserve user content.
- Check modes detect drift and write nothing.
out_of_scope:
- A new subagent runtime or a complete Claude permission engine.
- Lossy automatic rule activation and permission broadening.
- Global local-element migration and compatibility layers for older DSH versions.
- A generic future-target framework or automatic changes to user DSH profiles.
status_history:
- at: '2026-10-03T19:50:33+00:00'
  status: backlog
---

# DeepSeek Harness target support

## Intake

> support new target dsh(deepSeek harness)

> Давай продолжи и обязательно сверся с актуальной документацией по DSH

> 1. расширенный - полный возможный. 2. Project + global

> 1. Управляемый запуск 2. добавить

> брать текущую модель

## Why

An explicit dsh target currently installs no DSH artefacts. Users cannot reuse
their catalog or project-local Claude configuration with DeepSeek Harness.
The owner chose full feasible support in both project and user scope, including
native plugin-backed surfaces. The target must produce usable activation,
not just files, while preserving user configuration and reporting the precise
parts of Claude semantics that the pinned native APIs cannot represent.

## Goal and success metrics

Deliver a complete bounded DSH adapter over the existing target foundation.
"Full feasible" means every entry in the matrix below has an implementation or a
specific diagnosed native limitation, never a silent approximation. All four Q2
choices are accepted: full feasible support, project+global, managed launch and
the native fragment format. The remaining Q2 accepted the current DSH session
model for Claude-only aliases, with scope/name precedence stated in the question.
Implementation starts after an execution request; breakdown starts only after
independent review and Q3.

- [x] DSH-only and Claude+Codex+DSH manifests work in project and global scope,
  without changing the default target or existing empty/unknown-target behaviour.
- [x] Native skills, always-on instructions, callable catalog agents, supported
  command-hooks, MCP transports, environment settings and whole-tool permission
  gates are produced, activated, and covered by the matrix-specific tests.
- [x] Every unsupported input is reported with its origin, field/element and reason;
  permission gaps never enable a broader permission preset.
- [x] install/add/remove/status/reconcile and applicable -g/--check/--prune flags,
  domain add/remove, and project migrate --to dsh --dry-run handle DSH.
- [x] User files survive collisions/removal/prune, shared AGENTS.md blocks appear
  once, removed local sources retire owned outputs, and empty manifests clean up.
- [x] Managed artefacts carry source and generator provenance. status and check
  detect missing/stale files, resources and contributions; check/dry-run change
  no bytes, including activation or profile files.
- [x] A required isolated DSH 0.2.0-rc.2 smoke gate verifies loaded managed rows,
  callable child-agent composition, literal prompt bodies, permissions and fake
  MCP/hooks without production credentials or external service access.
- [x] README and the builtin ai-dotfiles skill describe the new workflow and
  native limitations in the same implementation PR.

## Research and tooling

Researched 2026-10-03 against current official docs/source
5badb15009ae1756c3afe0ae0cef1faafc290ccc (CLI 0.2.1-alpha.1).
Delivery baseline: published @deepseek-ai/dsh 0.2.0-rc.2, official tag commit
639ed015397290b3745d163aafe02ffee4aa3f84. npm latest/next was rechecked on
2026-10-04 and remains that release.
Relevant skill, instruction, subagent/spawn, tool policy, system-prompt,
hooks, include and profile-composition sources were compared with current docs
and are byte-identical. This is source-contract research, not runtime acceptance:
DSH and its dependencies have not been installed or run during planning.

| Choice | Version | Why |
|---|---|---|
| Official DSH native providers and plugin APIs | 0.2.0-rc.2 / 639ed015; current-doc snapshot 5badb150 | Implement the shipped contracts; no moving-preview or old-version shim. |
| Python/click and standard JSON | Python >=3.12,<4.0; click ^8.1, existing lock | Keep commands thin; JSON patch arrays are accepted by native YAML parsing. |
| Generated import-free ESM bridge plus Node composition helper | Node requirement declared by pinned DSH CLI | Preserve literal agent content and exact native tool gates; use DSH's parser instead of recreating YAML/!!js evaluation in Python. |
| Existing safe links, copy primitives, rule classifier and Markdown markers | Repository implementation | Preserve ownership and share instructions with Codex. |
| pytest/mypy/Ruff/Black and required native smoke fixture | Existing Poetry lock plus pinned DSH package | Python lifecycle tests and real native activation verify different contracts. |

Authoritative source groups; sources within a group ground its technical decision:

- Discovery: [filesystem provider](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/skill/skill-filesystem/README.md),
  [parser and Git-root algorithm](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/skill/skill-filesystem/src/index.ts),
  [home paths](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/util/home-paths/src/index.ts).
- Instructions/rules: [loader contract](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/context/agent-instructions/README.md),
  [files/activation](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/context/agent-instructions/src/files.ts),
  [Claude paths semantics](https://code.claude.com/docs/en/memory#path-specific-rules).
- Agents/bridge: [subagent tool schema](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/subagent/tool-subagent/src/index.ts),
  [child composition and approval](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/subagent/subagent/src/child-agent.ts),
  [prompt assembly/interpolation](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/core/system-prompt/src/index.ts),
  [local module loading](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/vendor/loader/src/index.ts).
- Composition/activation: [CLI workflow](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/apps/cli/README.md),
  [patch algorithm](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/vendor/include/src/index.ts),
  [exported composition/audit APIs](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/boot/app-boot/src/index.ts),
  [frozen CLI overlays](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/apps/cli/src/profile-boot.ts).
- Hooks: [plugin contract](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/hooks/hooks-claude-code/README.md),
  [parser](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/hooks/hooks-claude-code/src/config.ts),
  [payload/output handling](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/hooks/hooks-claude-code/src/index.ts).
- MCP/settings: [MCP schema](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/mcp/mcp-client/README.md),
  [official MCP example](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/docs/user/guide/mcp-memory.md),
  [model routing](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/core/agent-default-model/README.md),
  [settings writes](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/settings/settings/README.md),
  [published dependencies](https://registry.npmjs.org/@deepseek-ai/dsh/0.2.0-rc.2).
- Permissions: [gate API](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/docs/subsystems/tools.md),
  [one-shot approval](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/interaction/user-approval/README.md),
  [compound command semantics](https://code.claude.com/docs/en/permissions#compound-commands).
- Project binding: [workspace creation](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/workspace/workspace/src/index.ts),
  [workspace controller options](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/api/workspace-controller/src/index.ts),
  [session sandbox root](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/sandbox/sandbox-policy/README.md).

### Surface matrix

| Input | DSH implementation | Explicit boundary |
|---|---|---|
| Valid catalog/local skills | Native project .dsh/skills and user DSH_HOME/skills; full directory symlink/copy | DSH name/description/invocation schema validated; no Codex length truncation. |
| Always-on rules | Source-hashed AGENTS.md blocks where Codex/DSH classification agrees; otherwise a DSH-only literal prompt section | Preserve unconditional Claude activation for description-only rules without changing existing Codex classification. |
| Path-scoped rules | Keep original source/provenance; report exact activation gap | DSH directory/cwd/read activation differs from Claude globs. No broadening to a directory block and no silent skill demotion. |
| Explicitly on-demand rule/command content | Native skill when the source already declares that semantics | Commands with shell execution/import semantics are MANUAL, not falsely mechanical. |
| Agent body/description | One unique native subagent tool per catalog agent; stock in-process spawn plus prompt bridge | A registry preset alone is not an invokable type. Native parent composition is retained. |
| Agent tools/disallowedTools | Explicit known-name mapping to child allow/deny filters | An unrepresentable restriction makes the affected agent MANUAL; never drop it into unrestricted output. Filters are not a security boundary. |
| Agent model | Omitted/inherit and Claude-only aliases use the current parent session route; aliases retain provenance and emit MODEL_UNMAPPED; explicit native routes use the native fragment | Owner chose the current model at Q2; never invent provider/model ids or label alias loss as exact conversion. |
| Command hooks | One generated combined hooks.json, native compatibility plugin, copied handler resources | Seven supported events; handler/matcher/output gaps diagnosed as listed below. |
| MCP | Named native client rows; stdio and streamable-http, source cwd/args/env/headers | SSE and MCP prompt semantics are unmapped; do not silently change transport. |
| settings.env | Launcher child environment, global then project, explicit process env wins | Reserved DSH bootstrap variables rejected/reported; no dotenv-file writes. |
| permissions deny/ask | Known whole-tool names only; monotonic deny guard and preserving pre-execute ask waterfall | Constrained arguments, Bash expressions, unknown names and allow are reported; no full-access fallback. |
| DSH-specific settings/plugins | Domain dsh.fragment.json native patch array | Accepted at Q2; complete config replacement remains native semantics. |
| Local project elements | migrate --to dsh with classification/provenance; catalog copies excluded | Existing migrate is project-only; no new global migration switch. |

Hook boundaries are concrete: only SessionStart, UserPromptSubmit, PreToolUse,
PostToolUse, Stop, SubagentStart and SubagentStop with command handlers. Translate
known exact Claude tool-name matchers to native names. Report unsupported event
names, unknown matcher mappings and non-command/async/once options before DSH's
parser can ignore them. Native payload has empty transcript_path, flattened
PostToolUse output and general-purpose child type; raw scripts receive that
vocabulary. updatedInput, output rewrites, continue:false and systemMessage are
not applied by the pinned plugin. Report these compatibility limits for migrated
handlers; scripts with required incompatible behaviour are MANUAL. Exit-2,
native deny/ask, context and Stop-next-turn semantics are tested as supported.

The native fragment contract is finite: a domain-root dsh.fragment.json contains
one native patch array with JSON data only, no executable expression markers.
Use native composition/schema and the runtime audit to validate patch syntax,
targets and plugin configuration. Preserve existing dependency ordering, global
before project, and bind relative resources/plugins to their source domain.
Refuse unprovable dynamic targets/conflicts rather than evaluating them in
Python. Removal retires only the owned contribution/resources; native user files
and dependencies are not removed or rewritten.

Alternatives considered and rejected: a native-file-only target (owner rejected);
editing shared profile/home YAML (owner rejected at Q2); per-agent preset
clones (not selected by stock subagent tool and would duplicate whole plugin
composition); a new subagent engine (unnecessary); a full shell-aware permission
engine (unbounded beyond target translation); rewriting already-rendered PTC SDK
text (brittle). The prompt bridge instead appends a DSH-only literal description
roster; native schemas also retain source descriptions.

## Out of scope

- No emulation of arbitrary Claude glob activation, constrained permission
  expressions, full remembered allow grants or unsupported hook protocols.
  Preserve these sources and report them; do not claim parity where absent.
- No new subagent loop, shell parser/permission engine, hard Web workspace isolation,
  arbitrary custom-profile repair, or unsupported complete-persona prompt mode.
- No generic future-target adapter interface, feature flag, old-version
  compatibility shim, or automatic reinstall across all consuming projects.
- No global local-element migration or new init onboarding flags; catalog
  update/vendor/pull retain their existing non-auto-install contract.
- No modifications to user DSH package.json/profile/home patches in the recommended
  launch option. No automatic DSH runtime/package installation and no credentials.
- No repository-wide Claude/Codex cleanup; only their shared instruction
  coordination changes needed to preserve mixed-target ownership.

## Pre-decided decisions

1. Full feasible native-backed target, including callable agents, hooks, MCP,
   supported settings/permissions and applicable lifecycle/migration, size L —
   **ux,time; answered by owner at Q2**: "расширенный - полный возможный".
   [ADR ai-47xpm-1](../decisions/ai-47xpm-1_full-feasible-dsh-target.md).
2. Project and global delivery together, with project-only local migration as the
   current command's parity boundary — **ux,time; answered by owner at Q2**:
   "Project + global".
   [ADR ai-47xpm-2](../decisions/ai-47xpm-2_project-and-global-dsh-scopes.md).
3. Activation: new ai-dotfiles dsh launch command composes global/current
   project and supplies generated patches without modifying user profiles.
   One process uses one project's MCP/hooks/agents; restarting from another
   project is required, Web switching is not hard isolation — **ux,time; answered
   by owner at Q2**: "Управляемый запуск".
   [ADR ai-47xpm-3](../decisions/ai-47xpm-3_managed-dsh-launch.md).
4. Native format: domain dsh.fragment.json is a top-level JSON patch
   array, preserved as DSH configuration rather than mislabeled Claude translation —
   **ux,time,irreversible; answered by owner at Q2**: "добавить".
   [ADR ai-47xpm-4](../decisions/ai-47xpm-4_native-dsh-fragment-format.md).
5. Extend Target/RENDER_POLICY, paths and explicit element dispatch; use compact
   target-specific core modules and existing collectors/ownership helpers —
   **none; decided by agent**.
6. Faithful surfaces and gaps are exactly the matrix above, derived from accepted
   full-feasible scope and pinned native limits. No lossy directory/glob or
   permission conversion; retain per-origin diagnostics and MANUAL migration
   classifications when required semantics cannot survive —
   **none; decided by agent**, implements decision 1.
7. Generate import-free ESM bridge through a file-URL Cordis row. Whitelist exact
   generated persona-prefix text and set interpolate:false without replacing
   other sections; rewrite generated native tool descriptions and append a literal
   DSH-only roster for PTC/both and literal description-only unconditional rule
   sections. Do not add these DSH-only instructions to shared AGENTS.md.
   Stock child composition/spawn stays intact —
   **none; decided by agent**, required preservation in decision 1.
8. Permission bridge implements only exact known whole-tool deny/ask; ask preserves
   downstream deny/cancel/ask and never bypasses sandbox. Children with approval
   never reject ask; unsupported allow/argument patterns remain provenance+report.
   No custom permission engine —
   **none; decided by agent**, implements decision 1's faithful subset.
9. Stable namespace and scope merge: merge global then project contributions before
   Cordis insertion so logical agent/MCP names occur once; project wins for the
   same managed name. Conflicts with user id/tool/serverName stop activation;
   do not silently rename or override user rows. Hook resources retain origin and
   project/global path bindings — **ux,irreversible; answered by owner at Q2**:
   "брать текущую модель" selected the option whose question explicitly stated
   this precedence/collision policy and the included ownership coordinator cost.
   [ADR ai-47xpm-5](../decisions/ai-47xpm-5_dsh-model-inheritance-and-scope-precedence.md).
10. Shared project instruction union covers enabled Codex/DSH catalog plus both local
    provenance registries before remove/prune. Preserve Codex's existing rule
    classifier/policy; DSH-only unconditional description rules use the literal
    bridge instead of changing shared activation. The coordinator is necessary
    ownership plumbing within accepted project+global/full-feasible delivery —
    **none; decided by agent**, implements decisions 1 and 2.
11. Provenance covers source SHA, renderer generator, copy/link ownership, fragment
    contributions, resource tree and retired sources. Global prune visits only
    explicit owned roots/blocks. Check/dry-run never writes snapshots or profiles —
    **none; decided by agent**.
12. Pinned Node helper uses exported native composition APIs to return JSON to
    Python; no Python YAML/!!js interpreter. Dynamic conflicts that cannot be
    statically proved are refused with a reason. Runtime audit waits for Loader and
    checks every managed required id; ordinary DSH exit code is insufficient because
    optional plugin failure can merely warn —
    **none; decided by agent**.
13. Baseline is DSH 0.2.0-rc.2 at 639ed015, compared to current docs 5badb150.
    Validate official executable/package resolution and missing native providers
    before reporting readiness; user custom minimal profiles are not repaired —
    **none; decided by agent**.
14. Native fragment and launcher choices control configuration surface only.
    Profiles retain native full-config replacement; CLI overrides remain explicit,
    overlays are immutable during a process, and managed updates require restart —
    **none; decided by agent**, implementation of accepted decisions 3 and 4.
15. One final PR/branch epic/ai-47xpm, no mid-plan live step requires merged code.
    Planning creates no implementation branch/PR. Every phase names code/test/doc
    ownership; native runtime smoke is a required acceptance gate, not a skipped
    optional test masquerading as verification —
    **none; decided by agent**.
16. Claude-only model aliases retain source provenance and inherit the current
    parent DSH session route with MODEL_UNMAPPED. Explicit native routes remain
    native; omitted/inherit uses the current parent route —
    **ux; answered by owner at Q2**: "брать текущую модель".
    [ADR ai-47xpm-5](../decisions/ai-47xpm-5_dsh-model-inheritance-and-scope-precedence.md).

## Scope multipliers

- Necessary adapter/ownership helpers: DSH composition/assembly plus the narrow
  shared_instructions.py coordinator — needed to activate expanded surfaces,
  retain literal content and preserve mixed-target ownership. Price: generated
  ESM/Node helpers, coordinator and mixed-target/native runtime tests, included
  in the quoted L/approximately 2–3x scope; **owner answer yes at Q2** through
  full-feasible project+global delivery, reaffirmed in the model/precedence Q2
  question's explicit included L cost. These are required implementation
  helpers, not a generic future-target framework or independent product scope.
- Configurability through the native dsh.fragment.json —
  needed for native fields without Claude equivalents; price one public fragment
  contract/collector, composition validation and lifecycle tests;
  **owner answer yes at Q2 on 2026-10-04**: "добавить".
- No additional feature flag, dual old/new path, legacy-data import,
  backward-compat shim or future-target generalisation is included.

## Phases

Size **L**. Driver: two scopes, native runtime activation and callable agent bridge,
MCP/hooks/config/policy translation, local provenance and shared Codex/DSH cleanup.
This is the owner-selected approximately 2–3x native-file scope. Five ordered
milestones, at most five bounded subtask concerns per phase, one final shippable PR.
No deployed rehearsal occurs mid-plan; isolated installed-CLI testing is inside
the final PR and does not require an intermediate merge.

### Phase 0 — Contract, paths and shared instruction plan

Core targets.py/paths.py/elements.py and new dsh_targets.py/dsh_layout.py: exact
native skills/home roots and owned base .dsh/ai-dotfiles. B is project .dsh or
DSH_HOME; owned config/bridge/resources/provenance are below B/ai-dotfiles.
Global instructions are DSH_HOME/AGENTS.md; project blocks are shared AGENTS.md.
Add a narrow shared_instructions.py union coordinator for catalog+local desired
blocks. Native provider custom directories from the generated patch bind a nested
manifest's skill tree explicitly rather than pretending nearest Git root equals
manifest root; native-only launches still document Git-root discovery.

New tests: unit test_dsh_targets.py/test_dsh_paths.py/test_shared_instructions.py.
Cover .git file/worktree, nested manifest, non-Git root, DSH_HOME resolution and
mixed-target union. Gate: targeted unit suites, mypy, Ruff and Black checks.

### Phase 1 — Native elements and bounded runtime bridge

Implement dsh_render.py plus generated bridge template: validate skills, render
rule blocks, native named subagent rows, exact child filters and literal persona/
description mapping. Known aliases are diagnosed, native routes remain native.
Policy bridge uses whole-tool name mappings only. dsh_install.py manages linked/
copied skills and source/generator/resource provenance. Runtime audit module
establishes managed-row readiness and actionable failures.

New tests: unit test_dsh_render.py/test_dsh_permissions.py, integration
test_dsh_target.py/test_dsh_bridge.py. Cover descriptions including PTC roster,
literal double braces/whitespace, parent composition inheritance, filters,
denied/ask behaviour including approval never, invalid inputs and foreign files.
Gate: unit/integration plus a focused pinned native bridge fixture.

### Phase 2 — Configuration, hooks, MCP and activation

Implement dsh_config.py/dsh_hooks.py and dsh_native.py collector. Use
existing dependency ordering and domain collectors; preserve handlers and support
files under the owned resource tree independently of whether Claude is installed.
Translate only the matrix's supported MCP/hook/env fields and bind paths by origin.
Compose one merged snapshot, hooks.json and patch.json with namespace ownership.
Implement commands/dsh.py plus core dsh_launch.py and Node helper;
register only the command in cli.py. Launcher passes argv without a shell,
validates official CLI resolution, composes/audits current effective native
configuration, preserves explicitly supplied process env, and forwards exit status.
It never treats dump-config as read-only (native command may create profile files).

New tests: unit test_dsh_config.py/test_dsh_hooks.py/test_dsh_launch.py, integration
test_dsh_config_drift.py, e2e test_dsh_launch.py. Cover second-domain retention,
global/project precedence, HTTP/stdio fake services, event/matcher/output gaps,
no-shell argv, native override order, collision/expression diagnostics, native
fragment full-config replacement, readiness failure and restart notice.
Gate: targeted Python suites and pinned native composition/MCP/hook fixture.

### Phase 3 — Local migration and complete lifecycle

Implement dsh_migrate.py/dsh_local_registry.py/dsh_reconcile.py and wire
install/add/remove/status/reconcile/migrate/domain target dispatch. Preserve the
existing migration default, add --to dsh Choice/completion/help, keep --dry-run.
Exclude catalog domain symlinks AND copy-owned paths from local discovery;
track contributions/resources, classify MECHANICAL/REFACTOR/MANUAL, and retire
deleted sources through registry-versus-discovery reconciliation.
Local skills/agents/rules/settings/settings.local/.mcp.json/hooks/commands are
either converted through the same matrix or explicitly classified.
Both project/global catalog lifecycles and domain mutations honour selected
targets; prune/remove consult shared union and preserve local contributions.
Existing update/vendor/pull remain catalog-only. Integrate managed link paths with
gitignore policy without ignoring whole user AGENTS.md files.

New tests: integration test_dsh_migrate.py/test_dsh_reconcile.py/test_dsh_prune.py,
e2e test_dsh_install.py/test_dsh_global.py/test_dsh_migrate.py/test_dsh_domain.py.
Cover copy-mode exclusion, removed-source retirement, dry-run zero writes,
empty manifests, global bounded prune, shared blocks after single-target removal,
all existing applicable command flags and unknown/default target regression.
Gate: targeted suites plus full Python pytest and existing Codex lifecycle tests.

### Phase 4 — Runtime acceptance, documentation and final gates

Required tests/integration/test_dsh_runtime.py installs/resolves the exact pinned
DSH package only in a disposable fixture and uses local fake provider/MCP/hook
programs. Test startup/readiness, a real named child tool call, retained parent
services, literal prompt/description assembly, exact deny/ask and child approval
behaviour. No external provider requests or production configuration. Missing
runtime setup is a failed acceptance gate with diagnostics, not a silent skip.

Update README.md, builtin_ai_dotfiles_skill.md, new command/migrate help and source
templates/schema documentation; update pyproject test marker/resource packaging
only as needed for these shipped helpers. Document all matrix boundaries,
native fragment syntax, startup/restart/project binding, DSH_HOME,
native UI settings overridden by CLI patches, provenance and reconciliation.
Add isolated DSH_HOME/runtime fixtures to conftest.py; no test touches real home.

Final gates: poetry run pytest --cov (>=80%), required pinned native runtime suite,
poetry run mypy src/, poetry run ruff check src/ tests/,
poetry run black --check src/ tests/, and required pre-commit checks.
Runtime dependencies/domain bin shims reuse the existing machinery. No publication
or deployment is included.

## Decisions

- [ai-47xpm-1](../decisions/ai-47xpm-1_full-feasible-dsh-target.md) — owner selected
  full feasible support at Q2, superseding the native-file draft.
- [ai-47xpm-2](../decisions/ai-47xpm-2_project-and-global-dsh-scopes.md) — owner selected
  project+global together.
- [ai-47xpm-3](../decisions/ai-47xpm-3_managed-dsh-launch.md) — owner selected
  managed launch without profile changes, accepting process binding/restart.
- [ai-47xpm-4](../decisions/ai-47xpm-4_native-dsh-fragment-format.md) — owner selected
  the public native JSON patch fragment contract.
- [ai-47xpm-5](../decisions/ai-47xpm-5_dsh-model-inheritance-and-scope-precedence.md) —
  owner selected the current session model; its Q2 stated scope precedence,
  user-name collision refusal and the included ownership coordinator cost.

## Approval

Approved by owner at Q3 on 2026-10-04.
