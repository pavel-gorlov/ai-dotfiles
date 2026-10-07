# DeepSeek Harness target

The `dsh` target renders catalog configuration and migrated project-local
Claude content for **official `@deepseek-ai/dsh@0.2.0-rc.2`**. Managed activation
uses `ai-dotfiles dsh launch` and an existing native profile. Installing files
alone does not prove that their plugins, tools or restrictions are active.

This contract was checked on 2026-10-05 against the published RC2 runtime and
the [current official CLI documentation](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/README.md).
The immutable delivery reference is commit
[`639ed015`](https://github.com/deepseek-ai/deepseek-harness/tree/639ed015397290b3745d163aafe02ffee4aa3f84).
Current preview documentation can describe newer facilities, including
`sdk-minimal` and plugin peer-version exemptions; their presence in that
documentation is not a compatibility promise for this adapter. Older/newer
DSH runtimes and automatic custom-profile repair are unsupported.

## Enable a target and install

Run `ai-dotfiles init` in the project, then edit `ai-dotfiles.json`:

```json
{
  "packages": [],
  "targets": ["claude", "codex", "dsh"],
  "link_mode": "symlink"
}
```

Use `"targets": ["dsh"]` for DSH only. Without `targets`, the default stays
`["claude"]`; `init` adds no new target flag or DSH profile. Specifiers and
dependency ordering are unchanged:

```bash
ai-dotfiles add @gitflow skill:commit agent:reviewer
ai-dotfiles install
ai-dotfiles status
ai-dotfiles reconcile --check
```

These examples assume those elements exist in your catalog. `add` installs
them immediately; `install` also refreshes an existing manifest. `remove`
rebuilds the remaining contributions. `install --prune` cleans up proven owned
stale outputs; `--strict-deps` refuses missing transitive dependencies instead
of adding them. `--no-gitignore` is available on `install`, `add` and `remove`.

For user scope, add `"dsh"` to `targets` in
`$AI_DOTFILES_HOME/global.json` (default `~/.ai-dotfiles/global.json`):

```bash
ai-dotfiles add -g skill:commit
ai-dotfiles install -g --prune
ai-dotfiles status -g
ai-dotfiles reconcile -g --check
ai-dotfiles remove -g skill:commit
```

`global.json` supports all three targets too. `domain add NAME skill|agent|rule
ELEMENT_NAME` and `domain remove NAME skill|agent|rule ELEMENT_NAME` refresh
selected targets where the domain is installed globally or in the current
project; other projects refresh on their next install. Refused retirement
restores the catalog original. Catalog `update`, `vendor ... install` and
`pull` do not automatically refresh every consuming project or running DSH.

## Paths and ownership

| Surface | Project scope | User scope |
|---|---|---|
| Manifest | `<manifest-root>/ai-dotfiles.json` | `$AI_DOTFILES_HOME/global.json` |
| Native skills | `<manifest-root>/.dsh/skills/<name>/` | `$DSH_HOME/skills/<name>/` |
| Shared always-on instructions | `<manifest-root>/AGENTS.md` marker blocks | `$DSH_HOME/AGENTS.md` marker blocks |
| Managed configuration/resources | `<manifest-root>/.dsh/ai-dotfiles/` | `$DSH_HOME/ai-dotfiles/` |
| Local migration registry | `.dsh/ai-dotfiles/local.json` | No global local migration |

`DSH_HOME` defaults to `~/.dsh`; set it explicitly in the launching process to
use another native home. It is independent of `AI_DOTFILES_HOME`, which selects
catalog storage. Relative `DSH_HOME` follows native cwd resolution. Native
profiles remain under `$DSH_HOME/profiles/<name>/`.

The owned directory contains `config.json`, `patch.json`, `hooks.json`, generated
bridge/audit/launch helpers, `resources/` and `provenance.json`.
These are managed outputs. Edit the catalog/local originals, not these files.
The launcher recomputes from fresh originals and guarded ownership records;
stored aggregate `config.json` is never an activation source.

Skills retain the full directory, including scripts, references and assets.
Project `link_mode: "symlink"` is the default; `"copy"` copies the skill bundle
and is preserved by migration and managed launch. Copies require refresh after
source edits. Global CLI installs use links; there is no global copy flag.
Generated configuration and origin-bound resources have their own inventory.
Source SHA, renderer generator, source/resource trees and copy/link ownership
detect drift. Foreign or modified destinations are refused rather than replaced.

The manifest root may differ from DSH's nearest Git root, including nested
manifests and Git worktrees. Managed launch binds the manifest's skill directory
through the native provider instead of guessing discovery from cwd. A direct
native `dsh` launch retains native Git-root discovery and does not activate this
managed composition automatically.

## Managed launch

Install the official RC2 CLI and its Node runtime **separately**, make `dsh` and
`node` available on `PATH`, and prepare the native profile/provider configuration
with DSH's own tools. The managed launcher validates executable/package version
and required services; it neither installs DSH nor creates or repairs profiles.
Missing tools, providers or unprovable custom composition fail with diagnostics.

From the project's directory, use either profile spelling:

```bash
# Existing preset-free headless profile
ai-dotfiles dsh launch --profile headless "run the tests"
ai-dotfiles dsh launch headless "run the tests"

# Existing Web profile; --port and --no-open are native app arguments
ai-dotfiles dsh launch --profile web --port 8080 --no-open

# Explicit native JSON/YAML overlays, in order, before application arguments
ai-dotfiles dsh launch --profile headless --patch ./review.json --patch ./local.json "review the changes"
```

Supply `--profile` and repeatable `--patch` before native application arguments.
The first application argument ends launcher-option parsing; the remaining argv
is forwarded without a shell. There is no default profile, `-g` launch mode,
new permission preset or target opt-out flag. Profile creation, plugin management
and native config-dump commands belong to official `dsh`; config dumping is not
a promise of zero native profile writes.

The effective lower-to-higher order is **bundle order → profile patch → home
patch → managed global contributions → managed project contributions → explicit
CLI patches**. Dependencies retain catalog topological order. Project agents/MCP
names win over the same managed global name; hooks from both scopes remain in
one combined config, in order. Conflicting user row ids, tool names or MCP
server names stop activation instead of renaming or overwriting user entries.

Native patches replace an entry's **entire `config`**, not a deep merge. An
override must repeat every field you intend to retain. Explicit CLI patches
also take precedence over native UI-persisted settings. They do not rewrite the
user's profile or home patch. Native relative includes/modules still resolve
from their original profile, not the generated helper directory.

Managed source-custody checks and a settled native Loader audit of the actual
selected tree run in the **same host before Ready, surface release or a model
turn**. Every required managed id, tool, provider and service must be available.
An optional managed import/apply failure is fatal even when an ordinary native
optional plugin failure would only warn; process exit alone is not readiness.

RC2's stock headless consumer is global: a profile containing a selected managed
preset is refused with `COMPOSITION_NOT_SELECTED` before Ready/turn. A separately
mounted preset audit cannot make that consumer scoped. Use an existing
preset-free headless profile, or the preset-aware Web consumer (the native
`standard` preset was exercised with a real parent and named child).

Managed overlays are immutable during a process. The known official native HMR
path is disabled; refresh with `install`/`reconcile`, stop DSH and restart.
One process stays bound to the launching project's MCP, hooks and agents.
Restart from the other project when changing projects. Web workspace switching
does not provide hard isolation between these project configurations.

## Compatibility matrix

Diagnostics retain origin, element, source field and reason. `MANUAL` means
required semantics cannot be represented; it is not an unrestricted substitute.
Deferred YAML frontmatter is validated using the pinned native parser before
activation, not treated as a permanent skill limitation.

| Source surface | Supported result | Boundary |
|---|---|---|
| Skills | Native complete skill directories, name/description/invocation validation | No Codex description truncation. Invalid native names/metadata or Claude execution fields (`allowed-tools`, `context`, `agent`, `hooks`, `model`) are diagnosed. Native loading can trim the loaded body; the source bundle is not rewritten. |
| Always-on rules | Source-hashed `AGENTS.md` blocks when Codex/DSH classification agrees | Shared blocks are union-owned by enabled catalog targets and both local registries. Other contributors and user text survive removal. |
| Description-only unconditional rules | DSH-only literal prompt sections | They stay unconditional for DSH; Codex retains its existing synthetic skill classification. They are not added unconditionally to shared `AGENTS.md`. |
| Nonempty rule `paths` | Original source/provenance retained | DSH directory/cwd/read activation differs from Claude glob semantics. No directory broadening or automatic skill demotion. A conflicting effective shared Codex block can also refuse managed launch. |
| Explicit on-demand rules/commands | Native skill when the source already declares compatible invocation | Shell execution/import semantics and other unrepresentable command behavior are `MANUAL`; workflows have no automatic equivalent. |
| Agents | Named tool `ai_dotfiles_agent_<name>` with stock in-process spawn | Literal body and description retained, including native tool schema and PTC description roster. Child retains parent composition/services; no cloned preset or new agent engine. |
| Agent `tools` / `disallowedTools` | Exact known whole-name native child filters | Unknown/constrained restrictions make the affected agent `MANUAL`; they are not dropped. Filters are not a security boundary. |
| Agent `model` | Omitted/`inherit` uses the current parent session route | Claude aliases such as `sonnet`, `opus`, `haiku` also inherit it with `MODEL_UNMAPPED` and source-model provenance. No guessed provider/model id. Explicit native routes remain native fragment configuration. |
| `settings.env` | Global → project → explicit process environment | Process values, including empty strings, win. Reserved bootstrap names/prefixes are rejected; no dotenv writes. |
| `permissions.deny` / `.ask` | Exact known whole-tool gates | Argument patterns, compound Bash, wildcards and unknown names cannot be approximated. Unrepresentable deny/ask blocks activation; `allow` is reported and grants nothing. |
| Other Claude settings | Per-field diagnostic | Native settings/plugins belong in `dsh.fragment.json`; a Claude sandbox setting does not silently select a broader native preset. |
| Hooks | Seven command events below | Unsupported events/options/matchers and payload/output differences are explicit. |
| MCP | stdio and Streamable HTTP client rows | No SSE conversion or MCP prompt/OAuth/helper translation; see below. |
| Native settings/plugins | Domain-root `dsh.fragment.json` patch array | Native whole-config replacement/schema/selected-scope rules apply; no expressions or guessed dynamic targets. |
| Project-local content | `migrate --to dsh`, fresh-source provenance and reconciliation | Catalog-managed links/copies excluded; original ownership must be provable. No global local migration. |

The exact Claude-name map is `Read → read, read_image`, `Write → write`,
`Edit → edit`, `Glob → glob`, `Grep → grep`, `Bash → bash`,
`WebFetch → web_fetch`, `WebSearch → web_search`. Required native tools are
audited, including `read_image`; a missing image provider is not silently dropped.
`Task`, `Agent`, MCP families, already-native spellings and wildcards have no
proven Claude-name conversion. `Read()` and `Bash(git:*)` are not whole-tool
entries. Whole-tool deny remains monotonic; ask preserves downstream
deny/cancel/ask and the sandbox. A child with native approval `never` rejects ask
without an approval bypass. This is a bounded adapter, not a complete Claude
permission engine or a security isolation mechanism.

Both `ai-dotfiles.json` and `global.json` accept the optional top-level
`"dsh_permission_mode": "strict" | "native"`. Missing means `strict`;
invalid values fail. Strict mode blocks Claude `permissions.defaultMode`,
including `"auto"`, because it has no implemented native equivalent.

To retain Claude auto while using DSH's existing native policy, set
`"dsh_permission_mode": "native"` in the manifest of **each original source
scope** that contains `permissions.defaultMode: "auto"`. For global Claude
settings, use `~/.ai-dotfiles/global.json` (or `$AI_DOTFILES_HOME/global.json`);
a project choice cannot acknowledge a global source. This reports
`DEFAULT_MODE_NATIVE` as a nonblocking limitation, retaining the exact raw value,
source hash and provenance. `skipAutoPermissionPrompt` remains a nonblocking
`SETTINGS_FIELD_UNMAPPED` limitation.

This acknowledgement does not enable DSH Auto, select a preset, change approval
or sandbox defaults, or generate allow grants. Other defaultMode values, unknown
fields, invalid types and unrepresentable deny/ask entries still block. The
choice applies before source merging throughout install/add/remove, migration,
status/reconcile and fresh managed launch. Revoking it blocks affected activation
and prepared plans before writes or native readiness. After editing a manifest,
run `ai-dotfiles reconcile` in that scope (`-g` for global), then restart managed
DSH. Claude source files and native profiles remain unchanged.

## Hooks

All origins feed one generated `hooks.json` and
[`@deepseek-ai/dsh-hooks-claude-code`](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/hooks/hooks-claude-code/README.md).
Handler resources are copied with their source bindings independently of a
Claude installation. Project/global handler paths retain their origin;
raw scripts receive native tool names and native payloads, not rewritten bodies.

Only `type: "command"`, `command` and positive finite `timeout` (seconds) are
translated. Other events or options are diagnosed before the native parser can
ignore them: non-command `http`/`mcp_tool`/`prompt`/`agent` handlers, and
`args`, `async`, `asyncRewake`, `shell`, `if`, `once`, `statusMessage` are unsupported.
Handlers execute serially without deduplication; config is loaded once per
process. A runtime handler crash is logged by the native plugin and is not
itself a guaranteed run-level stop.

The reviewed stock `@gitflow` pair is a narrowly guarded exception to activation
refusal, **not** an `if` translation. Its exact context-only
`hooks/route-to-agent.sh`, unconditional `rules/gitflow.md` and
`agents/git-workflow-assistant.md` must match the reviewed catalog contents.
The selected catalog resource and effective rule/agent contributions must be
proved, including project-over-global precedence. The two reminders are retired
from DSH hooks with `HOOK_GITFLOW_POLICY_FALLBACK`, retaining their originals and
source hashes. Routing remains in the always-on policy and the callable native
`ai_dotfiles_agent_git-workflow-assistant`; its model inherits the current session.
The additional **per-command hook nudge is absent**: the bridge ignores
PreToolUse `additionalContext`. Managed launch still requires actual policy
delivery and agent availability through its native composition/selected-tree
audit before Ready or a model turn. Changed or missing stock sources, an
unproved local/custom origin, or unavailable policy/agent retain one actionable
blocking `.if` diagnostic per stock reminder. Unrelated problems are still
reported. Other `if` handlers and required hook semantics remain blocked. This
same guard applies to project/global catalog lifecycle and project-local
migration; it does not edit Claude/Codex originals or profiles.

| Event | Supported behavior | Payload/output limits |
|---|---|---|
| `SessionStart` | Event-keyed JSON `additionalContext` | Plain stdout context, `initialUserMessage`, `sessionTitle`, `watchPaths`, `reloadSkills`, `CLAUDE_ENV_FILE` unsupported. Detached context can miss the first request; `model`, `agent_type`, `session_title` omitted. |
| `UserPromptSubmit` | Block prompt or event-keyed JSON context | Plain stdout context, `sessionTitle`, `suppressOriginalPrompt` unsupported. Default timeout 600 seconds, not Claude's event-specific 30 seconds. |
| `PreToolUse` | Native deny/ask and exit-2 denial | `allow` does not pre-approve; `defer`, input rewrite (`updatedInput`) and `additionalContext` unsupported. |
| `PostToolUse` | Blocking feedback or event-keyed JSON context | `tool_response` is flattened text. `updatedToolOutput`/`updatedMCPToolOutput` do not rewrite output. |
| `Stop` | Blocking reason/exit 2 steers another turn | `stop_hook_active` always false; no consecutive-block cap. `last_assistant_message`, `background_tasks`, `session_crons` omitted. Hooks must self-limit repeated continuation. |
| `SubagentStart` | Best-effort context to a live in-process child | Constant `agent_type: general-purpose`; `session_id` is the child's. Remote-child delivery not guaranteed. |
| `SubagentStop` | Observation only | Cannot block/add context, including exit 2. Same constant type/child id; empty/absent transcript information, `last_assistant_message`, `background_tasks`, `session_crons` omitted; `stop_hook_active` false. |

Every payload has `session_id`, `cwd`, `hook_event_name` and an **empty**
`transcript_path`; no readable transcript file is supplied. Common optional
`prompt_id`, `permission_mode`, `effort` are absent. `systemMessage` is logged,
not surfaced; `continue: false` does not halt the run. `suppressOutput`,
`stopReason`, `terminalSequence` are not applied.

Tool-event matchers accept exact known Claude names and pipe alternatives
(`Read|Grep` becomes `read|read_image|grep`); no unknown names or arbitrary regex
conversion. `SessionStart` matches `startup|resume|clear|compact`; subagent events
can match only `general-purpose`. `UserPromptSubmit`/`Stop` ignore native
matchers, so a supplied constraint cannot be preserved. Empty/`*` matchers remain
unconditional.

Return context in the event-keyed JSON shape, for example:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "Use the project review checklist."
  }
}
```

Exit 2 supports blocking/feedback/continuation only at the applicable prompt,
tool and Stop events. It cannot turn observation-only subagent-stop into a veto.
Compatibility diagnostics do not inspect arbitrary script behavior: handlers
requiring a missing payload/output semantic need manual adaptation.

## MCP and environment

Domain `mcp.fragment.json` uses the existing `mcpServers` object. For stdio,
`command`, literal string `args`, string `env` and `cwd` are preserved; commands
are argv, not shell expressions. Relative executable paths and cwd bind to the
origin's resources. HTTP requires explicit `type: "http"` or
`"streamable-http"`, an HTTP(S) `url` and string `headers`. Native server names
must match `[A-Za-z0-9_-]{1,32}`. Each managed client must start successfully.
See the [native MCP client contract](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/mcp/mcp-client/README.md).

SSE, MCP prompts and unrepresentable OAuth/helpers are diagnosed, never silently
converted. Claude `${VAR}` / `${VAR:-default}` placeholders in args/env/headers
have no proved equivalent expansion/redaction contract and produce
`MCP_ENV_UNMAPPED`. Launcher environment precedence does not implement that
interpolation. Configure actual credentials through your native provider/host
setup; no credential literals are needed in catalog examples.

`settings.env` cannot set bootstrap names such as `HOME`, `PATH`, `NODE_OPTIONS`,
proxy/TLS overrides, or prefixes `DSH_`, `XDG_`, `DYLD_`, `BASH_FUNC_`.
`ENV_RESERVED` directs those choices to the explicit launching environment.
Do not confuse this supported env projection with uncertain local ownership.

## Native fragment example

Create `catalog/review-tools/dsh.fragment.json` as a **top-level patch array**:

```json
[
  {
    "insert": [
      {
        "id": "review-notice",
        "name": "./notice.mjs",
        "config": {"message": "Review tools loaded", "verbose": false}
      }
    ]
  },
  {
    "id": "review-notice",
    "config": {"message": "Project review tools loaded"}
  }
]
```

The matching domain resource `notice.mjs` can be a native plugin:

```javascript
export function apply(ctx, config) {
  ctx.logger.info(config.message);
}
```

The second patch replaces the first `config`: `verbose` is gone. ai-dotfiles
copies the domain resources and binds `./notice.mjs` to that source-owned copy.
Known native Include paths, skill directories and MCP bindings receive the same
origin discipline. Paths that escape their source or unknown plugin-relative
resource semantics are refused; provide a proven explicit native binding.

The file contains JSON data only: no YAML `!!js` or `__jsExpr` executable markers.
Native composition validates patch targets and plugin schemas. Dynamic targets,
unprovable includes and foreign-name conflicts are not guessed or evaluated in
Python. `ai-dotfiles add @review-tools`, then managed launch with your existing
profile activates the domain; removal retires only its owned contribution and
resources, preserving native profiles, home patches and user dependencies.

## Local migration, drift and retirement

```bash
ai-dotfiles migrate --to dsh --dry-run
ai-dotfiles migrate --to dsh
ai-dotfiles status
ai-dotfiles reconcile --check
ai-dotfiles reconcile
```

`migrate` defaults to Codex and remains project-only (no `-g`). Dry-run classifies
`MECHANICAL`, `REFACTOR` and `MANUAL` actions without changing any source,
registry, activation or profile bytes. DSH can preserve valid local skills,
agents, compatible rules/on-demand commands and supported raw settings, hooks
and user MCP contributions. Catalog links, domain links and copy-owned content
are excluded from local adoption.

The preview labels diagnostics `BLOCKER` or `LIMITATION` and reports activation
as `BLOCKED` or `READY for apply`. A blocked preview never recommends applying;
resolve its config/hook/permission blockers first. Individual `MANUAL` elements
remain inactive even when the supported contributions are ready. Apply readiness
is a source/configuration preflight, not proof of native runtime readiness;
the managed launch audit is still required. `ALLOW_UNMAPPED` and the verified
stock gitflow policy fallback are nonblocking limitations and grant nothing.

Mixed-target settings/MCP are projected from fresh originals and their ownership
ledgers, with present/absent guards. Supported user permissions/hooks/MCP are
joined with catalog sources once. An aggregate env/scalar field whose original
user origin cannot be proved remains `LOCAL_ORIGINAL_UNPROVEN` and blocks
activation. Equal values are not proof of origin. Preserve or establish an unambiguous original rather
than deleting ledgers or activating an old snapshot.

Catalog `install`/`add`/`remove` and launch preserve already registered locals
without automatically adopting new unregistered local elements. Full migration/
reconciliation handles discovery and retires disappeared sources. Retired or
disabled native-discovered assets need verified removal or a launch refusal;
mere omission from a new config is not enough. Shared Codex/DSH blocks retire
only after both catalog/local contributor sets and historical custody are checked.
Collisions and modified managed outputs preserve the existing user/foreign bytes.

`status` and `reconcile --check` detect source, generator, output, resource and
contribution drift. Check/dry-run write zero bytes; a clean drift check is not
native readiness. `reconcile` regenerates and retires owned outputs when custody is
proved. After any managed change, restart DSH so the same-host selected-tree
audit can validate the new composition.
