---
name: ai-dotfiles
description: Manage Claude Code configuration via the ai-dotfiles CLI — install/add/remove skills, agents, rules and domains; scaffold new elements; vendor external sources from GitHub, paks or skills.sh; validate symlinks in ~/.claude/.
when_to_use: Trigger when the user mentions "ai-dotfiles", "~/.ai-dotfiles/", "AI_DOTFILES_HOME", "ai-dotfiles.json" or "global.json"; adds/removes/installs/lists a skill, agent, rule or domain for Claude Code; scaffolds a new element; vendors external content (GitHub, paks, npx skills CLI, buildwithclaude, tonsofskills, mattpocock, printingpress); checks the health of Claude Code symlinks under ~/.claude/ or <project>/.claude/; reconciles ai-dotfiles.json or global.json with the filesystem.
---

# ai-dotfiles

Use this skill when the user asks to install/add/remove Claude Code configuration elements, scaffold new skills/agents/rules, work with domains, or vendor external sources via the `ai-dotfiles` CLI.

Prefer running the CLI over editing `~/.claude/` or manifests by hand — manifests and symlinks must stay in sync.

## Commands

### Setup

- `ai-dotfiles init` — create `ai-dotfiles.json` in the current project.
- `ai-dotfiles init -g` — scaffold global storage at `~/.ai-dotfiles/` (override via `AI_DOTFILES_HOME`). Pre-existing files in `~/.claude/` (`CLAUDE.md`, `settings.json`, hooks, output-styles) are **adopted** — they replace the scaffold templates inside `global/` and are then symlinked back, so your previous config stays authoritative and no backup dir is created.
- `ai-dotfiles init -g --from <git-url>` — clone an existing storage repository. Conflicting local files under `~/.claude/` are moved to `~/.dotfiles-backup/` (the cloned content wins).
- `ai-dotfiles update` — refresh CLI-managed files inside an existing storage. Today: rewrites the built-in `ai-dotfiles` skill (`catalog/skills/ai-dotfiles/SKILL.md`) from the installed CLI's template. User-authored skills/agents/rules/manifests and `global/` content are never touched. Run after upgrading the CLI.
- `ai-dotfiles pull [--rebase]` — if the storage is a git repo, fetch and fast-forward from the configured remote. Refuses on a dirty worktree or on divergence; `--rebase` replays local commits on top of the remote tip. Prints a hint to run `install -g` afterwards so updated global content is re-linked.
- `ai-dotfiles completion install [--shell bash|zsh] [--print]` — install tab completion. Writes the Click-generated script to `~/.ai-dotfiles/completions/ai-dotfiles.<shell>` and patches `~/.bashrc` / `~/.zshrc` with a marker-guarded source block (idempotent — safe to re-run). Auto-detects the shell from `$SHELL`; `--print` emits the script to stdout without touching any files.
- `ai-dotfiles completion uninstall [--shell bash|zsh]` — remove the completion block from the rc file and delete the cached script.

After installing completion, arguments themselves tab-complete too:

- `add <TAB>` / `add -g <TAB>` — catalog specifiers, fresh-first (not yet installed), installed last; scope follows `-g`.
- `remove <TAB>` / `remove -g <TAB>` — only specifiers already in the manifest for that scope.
- `domain delete|list <TAB>` — existing domain names; `domain remove <name> <type> <TAB>` — elements of that type in that domain.
- `delete skill|agent|rule <TAB>` — existing standalone elements of the preceding type.
- `vendor remove <TAB>` — names with `.source` sidecars in the catalog.

### Packages

- `ai-dotfiles install` — symlink packages listed in `ai-dotfiles.json` into `<project>/.claude/`.
- `ai-dotfiles install -g` — symlink packages from `global.json` into `~/.claude/`.
- `ai-dotfiles install --prune [-g]` — after linking, also remove stale symlinks under `~/.claude/` (or `<project>/.claude/`) that point into storage but no longer resolve — useful after renaming or deleting a catalog element, or after a pull that changed catalog layout. User-owned symlinks pointing outside ai-dotfiles storage are left alone.
- `ai-dotfiles install --strict-deps [-g]` — refuse to install if the manifest is missing any transitive dependencies. Without this flag, missing deps are auto-added to the manifest and a warning is printed.
- `ai-dotfiles add <spec>...` — add specifiers to the **project** manifest (`ai-dotfiles.json`) and symlink into `<project>/.claude/`. Transitive deps declared via `domain.json` (or frontmatter `depends:` for standalone elements) are pulled in automatically and prepended to the manifest in topological order.
- `ai-dotfiles add -g <spec>...` — add specifiers to the **global** manifest (`~/.ai-dotfiles/global.json`) and symlink into `~/.claude/`.
- `ai-dotfiles remove <spec>...` — remove from project manifest and unlink. Refuses if other manifest entries declare a dependency on the target; pass `--force` to break the dependency anyway, or remove the dependents in the same call.
- `ai-dotfiles remove -g <spec>...` — remove from global manifest and unlink.
- `ai-dotfiles list` / `list -g` — show installed packages (project / global). Each entry is colour-coded: **green** for direct installs, **yellow** for entries pulled in transitively (the parent specifiers are appended in parens, space-separated). The project block additionally tags entries that also live in `global.json` with a trailing `(g)` suffix; the global block omits the suffix because every line is global by definition.
- `ai-dotfiles list --available` — list everything present in the catalog. Same colour scheme; `(g)` is shown on every globally-installed entry.
- `ai-dotfiles status` — report symlink health and a settings summary. In a project it also lists **LOCAL (non-catalog) elements** and whether each has been migrated to Codex, plus **Claude-only** surfaces (workflows, custom commands) that have no Codex home.
- `ai-dotfiles status -g` — same for the global scope. When `codex` is in `global.json`'s `targets`, a `Codex target (global)` section reports every `$CODEX_HOME` artefact as OK / STALE / NOT INSTALLED — including symlinked skills (flagged when the source description outgrows Codex's 1024-char cap), the `AGENTS.md` instructions bridge, and `config.toml` drift.

### Codex migration

These commands carry a project's own hand-authored config to the Codex target and keep every target fresh:

- `ai-dotfiles migrate [--to codex] [--dry-run]` — migrate **LOCAL** (hand-authored, non-catalog) `.claude/` skills/agents/rules to Codex. A skill is a relative symlink `.agents/skills/<name>` → `../../.claude/skills/<name>` when its raw `SKILL.md` is within Codex's 1024-char `description` cap and the name is valid hyphen-case (auto-fresh, no drift); otherwise it is rendered with the first-sentence trim. Agents render to `.codex/agents/<name>.toml`; rules dispatch like catalog rules (synthetic `rule-<name>` skill or `AGENTS.md` block). `CLAUDE.md` stays the canonical instruction file — migrate points Codex at it via `project_doc_fallback_filenames` in `.codex/config.toml` (no rendered copy, no symlink). User-authored `.mcp.json` servers (not domain-owned) are copied to `[mcp_servers]`. Provenance is recorded in `.codex/.ai-dotfiles-local.json` so `install --prune` keeps migrated artefacts. `--dry-run` plans and classifies (MECHANICAL / REFACTOR) and lists Claude-only surfaces, writing nothing.
- `ai-dotfiles reconcile [--check]` — regenerate stale or missing Codex artefacts (catalog **and** migrate-origin), the missing feedback loop after the first `install`. Reuses the drift checks (`is_stale`, rule-block sha, `config.toml` recompute) plus local-source freshness; symlinked local skills are auto-fresh, so only a broken link counts as drift. `--check` writes nothing and exits non-zero on any drift — a CI / pre-commit gate.
- `ai-dotfiles reconcile -g [--check]` — same for the **global** Codex scope (`$CODEX_HOME`): refreshes stale renders, the `~/.claude/CLAUDE.md` instructions bridge, the managed `config.toml` regions, and converts a symlinked skill to a render when its source outgrows Codex's 1024-char description cap (and back). No-op with a hint when `codex` is not in `global.json`'s `targets`.

> `migrate` works whether or not `codex` is in `targets` (it is a project-local action); `reconcile` refreshes catalog artefacts only when `codex` is in `targets`, and always refreshes migrate-origin local artefacts.

### Elements

- `ai-dotfiles create skill|agent|rule <name>` — scaffold an element in the catalog.
- `ai-dotfiles delete skill|agent|rule <name>` — remove an element from the catalog.
- `ai-dotfiles domain create|delete|list <name>` — manage domains (a folder under `catalog/`).
- `ai-dotfiles domain add|remove <domain> <type> <name>` — manage elements inside a domain. If `@<domain>` is referenced by `~/.ai-dotfiles/global.json` or by the current project's `ai-dotfiles.json`, the new element is auto-linked into the matching `.claude/` (and unlinked on `remove`) — no follow-up `install` needed for that scope.

> Need an opinionated bundle? Create a meta-domain with `depends: [...]` in `domain.json` and `add @your-bundle` — see `### Dependencies between elements` below. The legacy `stack` command is gone.

### Vendors

Vendors import external skills/agents/rules into `catalog/` and write a `.source` sidecar (origin, fetch date, license). After install, the CLI prints the `ai-dotfiles add` line to wire the item into a manifest.

Meta commands (vendor-agnostic):

- `ai-dotfiles vendor list` — registered vendors and whether their host deps (git, npx, paks, ...) are on `PATH`; shows install URL for any missing dep (useful before running `deps install`).
- `ai-dotfiles vendor installed` — every catalog entry that came from a vendor (reads `.source`).
- `ai-dotfiles vendor search <query> [-v NAME ...] [--limit N]` — one shot across every vendor whose deps are installed; results grouped by vendor.
- `ai-dotfiles vendor remove <name> [--kind skill|agent|rule] [-y]` — delete a vendored entry.

Per-vendor subcommands follow the same shape — `install / list / search / deps check / refresh` (only the vendors that support caching expose `refresh`):

| Vendor | Source format | Extra | Host dep |
|--------|---------------|-------|----------|
| `github`          | repo URL or `/tree/<branch>/<subpath>` URL | — (no `search`) | `git` |
| `skills_sh`       | `<org>/<repo>` (npm `skills` CLI source) | `search`, `--select a,b` on install | `npx` (Node.js) |
| `paks`            | `<skill-name>` (one source = one skill) | `search` | `paks` binary (`brew tap stakpak/stakpak && brew install paks`) |
| `buildwithclaude` | `<skill-name>` from cached catalog | `search`, `refresh` (24h TTL) | `git` |
| `tonsofskills`    | `<skill-name>` from cached catalog | `search`, `refresh` (24h TTL, slow first fetch — 20k files) | `git` |
| `mattpocock`      | `<skill-name>` from cached catalog (mattpocock/skills) | `search`, `refresh` (24h TTL) | `git` |
| `printingpress`   | `<skill-name>` from cached catalog (mvanhorn/printing-press-library) | `search`, `refresh` (24h TTL) | `git` |

All `install` commands accept `-f/--force` (overwrite existing catalog entry). `skills_sh` additionally accepts `--select a,b,c` to install a subset.

#### Typical per-vendor flow

```bash
# GitHub (direct subtree clone)
ai-dotfiles vendor github install \
  https://github.com/anthropics/skills/tree/main/skills/pdf
ai-dotfiles add skill:pdf

# skills.sh (npm-backed marketplace)
ai-dotfiles vendor skills_sh deps check
ai-dotfiles vendor skills_sh search react
ai-dotfiles vendor skills_sh install vercel-labs/agent-skills --select deploy-to-vercel
ai-dotfiles add skill:deploy-to-vercel

# paks (stakpak registry, one-skill-per-source)
ai-dotfiles vendor paks deps check
ai-dotfiles vendor paks search kubernetes
ai-dotfiles vendor paks install kubernetes-deploy
ai-dotfiles add skill:kubernetes-deploy

# buildwithclaude (cached marketplace)
ai-dotfiles vendor buildwithclaude refresh          # prime cache (once)
ai-dotfiles vendor buildwithclaude search typescript
ai-dotfiles vendor buildwithclaude install mcp-builder
ai-dotfiles add skill:mcp-builder

# tonsofskills (cached marketplace; first refresh is slow)
ai-dotfiles vendor tonsofskills refresh
ai-dotfiles vendor tonsofskills search kubernetes
ai-dotfiles vendor tonsofskills install generating-database-seed-data
ai-dotfiles add skill:generating-database-seed-data

# mattpocock (cached marketplace; Matt Pocock's personal .claude/skills)
ai-dotfiles vendor mattpocock refresh
ai-dotfiles vendor mattpocock search tdd
ai-dotfiles vendor mattpocock install tdd
ai-dotfiles add skill:tdd

# printingpress (cached marketplace; printingpress.dev / mvanhorn library)
# Each skill bootstraps its own prebuilt CLI binary via npx on first use
# (Go install is the fallback if Node is unavailable). Vendor itself only
# needs `git`.
ai-dotfiles vendor printingpress refresh
ai-dotfiles vendor printingpress search openalex
ai-dotfiles vendor printingpress install pp-openalex
ai-dotfiles add skill:pp-openalex
```

Cache path for `refresh`-capable vendors: `~/.ai-dotfiles/.vendor-cache/`. `search` / `install` auto-refresh when the cache is older than 24h; pass `--force` to skip the TTL check.

Install ≠ activate. `vendor <name> install` only fetches content into `catalog/`. You still need `ai-dotfiles add [-g] <spec>` + `install` to link it into `.claude/`.

### Specifier syntax

Specifiers are the strings that appear in `packages` arrays:

- `@domain` → `catalog/<domain>/` (whole domain directory).
- `skill:name` → `catalog/skills/<name>/` (directory with `SKILL.md`).
- `agent:name` → `catalog/agents/<name>.md`.
- `rule:name` → `catalog/rules/<name>.md`.

### `targets` — multi-target manifests

The `targets` array in `ai-dotfiles.json` declares which agent CLIs the project renders its catalog elements to:

```json
{ "packages": ["@gitflow", "skill:commit", "agent:reviewer"], "targets": ["claude", "codex"] }
```

| Value | Meaning |
|-------|---------|
| `"claude"` | Claude Code — the default; installs into `<project>/.claude/` as before |
| `"codex"` | OpenAI Codex CLI — installs into `<project>/.agents/skills/` and `<project>/.codex/agents/` |

Absent `targets` field → `["claude"]`. Every existing manifest keeps working unchanged.

**The global scope supports Codex too.** `global.json` accepts the same `targets` field; with `"targets": ["claude", "codex"]`, `install -g` / `add -g` / `remove -g` / `status -g` / `reconcile -g` also render the global packages into Codex's **user scope** (`$CODEX_HOME`, default `~/.codex` — the same env override Codex itself honours), making them available in every Codex session without per-project manifests. Without the field, behaviour stays Claude-only and byte-identical.

#### What `"codex"` produces at GLOBAL scope (`install -g`)

| Element | Output path | Strategy |
|---------|------------|----------|
| skill (within limits) | `$CODEX_HOME/skills/<name>` | **Absolute symlink** into the catalog — auto-fresh, no drift tracking. Gated: the frontmatter `description` must be ≤ 1024 chars and the name valid hyphen-case, else the whole skill would silently fail to load in Codex |
| skill (over cap / bad name) | `$CODEX_HOME/skills/<name>/` | Rendered with the first-sentence description trim + `.ai-dotfiles-meta` drift sidecar (same as project scope) |
| agent | `$CODEX_HOME/agents/<name>.toml` | Rendered TOML with the `# source-sha256` drift header |
| always-on rule | `$CODEX_HOME/AGENTS.md` managed block | Same marker + sha discipline as project blocks |
| path-scoped rule | `$CODEX_HOME/skills/rule-<name>/` | **Demoted** to a synthetic rule-skill (warned): there is no project tree, so no per-directory `AGENTS.md` surface — the path scoping is lost, the content stays available on demand |
| description-only rule | `$CODEX_HOME/skills/rule-<name>/` | Synthetic rule-skill, as in project scope |
| `~/.claude/CLAUDE.md` | `$CODEX_HOME/AGENTS.md` managed block `claude-global-instructions` | The global instructions bridge — drift-tracked via the block's sha marker; refreshed by `install -g` / `reconcile -g` |
| domain `settings.fragment.json` / `mcp.fragment.json` | `$CODEX_HOME/config.toml` | Managed `[ai_dotfiles]` region + `[mcp_servers]` with the ownership sidecar; the user's own keys/tables/servers are preserved |
| domain hooks | `$CODEX_HOME/hooks.json` | Translated hook groups with the per-group signature sidecar — user/other-tool hook groups (e.g. moshi's) survive every write |

`install -g` also adds `CLAUDE.md` to `project_doc_fallback_filenames` in `$CODEX_HOME/config.toml`, so any project that has only a `CLAUDE.md` is readable by Codex without a per-project `migrate`.

`$CODEX_HOME/config.toml`, `hooks.json` and `AGENTS.md` are **shared files the user already owns** — every write goes through the managed-region / signature-sidecar / marker-block discipline, and `remove -g` / `install -g --prune` strip only ai-dotfiles-owned entries (prune identifies our skill symlinks by "resolves into the catalog"). The rule name `claude-global-instructions` is reserved for the bridge.

**Duplication:** an element installed both globally and in a project renders twice (user scope + project scope). The global scope cannot know every project, so this is accepted by design. Verified on Codex CLI 0.143 (`codex debug prompt-input`): Codex does **not** de-duplicate by name — *both* entries appear in the session's skill list. Nothing breaks, but the prompt carries two same-named skills; prefer keeping an element in only one scope when that bothers you (`remove` it from the project manifest once it goes global).

### `link_mode` — symlink vs copy for the Claude target

The optional top-level `link_mode` field in `ai-dotfiles.json` controls how the **Claude target** materialises skills/agents/rules into `<project>/.claude/`:

```json
{ "packages": ["@gitflow", "skill:commit"], "link_mode": "copy" }
```

| Value | Meaning |
|-------|---------|
| `"symlink"` | The default. `.claude/` entries are symlinks into `~/.ai-dotfiles/catalog/` — a live view of the catalog. Right choice on Linux / WSL. |
| `"copy"` | `.claude/` entries are **real copied files**. Use on a native-Windows host whose catalog lives in WSL: native Windows cannot resolve a symlink that points into the WSL filesystem, so every `.claude/` entry would appear broken / 0-byte. |

Absent `link_mode` field → `"symlink"`. Every existing manifest keeps byte-identical behaviour. An unknown value is rejected with an error.

**A copy is a snapshot, not a live view.** Unlike a symlink, a copied `.claude/` entry does not track the catalog — after a catalog change (a `pull`, an edit, a vendored update) re-run `ai-dotfiles install` to refresh the copies.

`install` / `add` copy instead of symlink; `remove` and `install --prune` delete stale copies (a `.ai-dotfiles-copies.json` sidecar under `.claude/` records which entries are ai-dotfiles-managed, so user-authored files are never touched); `status` reports copies as `OK (copied)` rather than flagging them as unmanaged. `link_mode` is a project concern only — the global scope (`-g` commands) always uses symlinks, since the global `~/.claude/` sits next to the catalog.

#### What `"codex"` produces

| Element | Output path | Format |
|---------|------------|--------|
| `skill:name` or domain skill | `.agents/skills/<name>/` | Real directory with a generated `SKILL.md` (first-sentence `description`) + copied support files (`scripts/`, `references/`, `assets/`, …) — the Codex target is fully self-contained, no symlinks into the catalog |
| `agent:name` or domain agent | `.codex/agents/<name>.toml` | Generated TOML (`name`, `description`, `developer_instructions`) — a committed project artefact. A frontmatter `model` is **not** carried over: see below |
| `rule:name` or domain `rules/` member | See rule classes below | Dispatched by rule frontmatter — three possible outputs |
| Domain `hooks/` members | `.codex/hooks.json` references them | Scripts stay in `.claude/hooks/`; the hook entries in `hooks.json` reference them (an info note reminds you to keep the Claude target installed so they resolve) |
| Domain `settings.fragment.json` | `.codex/config.toml` `[ai_dotfiles]` + `.codex/hooks.json` + `.codex/rules/ai-dotfiles.rules` | `permissions` → exec-policy `prefix_rule` entries (see below) and, as a record of the source lists, the `[ai_dotfiles]` table; `sandbox` → config.toml; `hooks` → hooks.json |
| Domain `mcp.fragment.json` | `.codex/config.toml` `[mcp_servers]` table | Each server entry written as a `[mcp_servers.<name>]` sub-table; ownership in `.codex/.ai-dotfiles-mcp-ownership.json` |

#### Permissions → the Codex exec policy

Claude gates shell commands with `permissions` entries (`Bash(git fetch:*)`). Codex gates them with an **exec policy**: Starlark `.rules` files scanned from a `rules/` directory — `<repo>/.codex/rules/` at project scope, `$CODEX_HOME/rules/` at global scope.

ai-dotfiles writes two files there and never touches a third:

| File | Written by | Contents |
|---|---|---|
| `ai-dotfiles.rules` | `install` / `add` / `remove` | catalog domain permission lists |
| `ai-dotfiles-local.rules` | `migrate` | the project's own entries (`settings.local.json`, plus anything hand-added to `settings.json`), minus what the catalog already covers |
| `default.rules` | **Codex itself** | the approvals you grant in the TUI — ai-dotfiles never writes it |

```python
prefix_rule(
    pattern = ["git", "fetch"],
    decision = "allow",
    justification = "ai-dotfiles: Bash(git fetch:*)",
)
```

`allow` → `allow`, `deny` → `forbidden`, `ask` → `prompt`. Layers merge by *most restrictive* (`forbidden` > `prompt` > `allow`). Codex echoes the `justification` verbatim when it blocks a command, so a block names the catalog entry that caused it.

**Entries that would grant more than you wrote are not translated.** `prefix_rule` matches a token prefix, so `Bash(pg_isready)` — an exact command — would become "`pg_isready` with any arguments". Rather than quietly widen a grant, these are reported and left out:

- an exact command with no trailing `*`;
- an argument list with shell syntax (quotes, pipes, redirects) — `Bash(curl … -d '{…}')`;
- a wildcard anywhere but the end;
- a non-`Bash` tool (`Read()`, `WebFetch()`, `mcp__*`) — the exec policy governs command execution only.

`status` reports the file as `STALE (permissions changed)` when the fragments no longer match it; `install` and `reconcile` regenerate.

Caveat inherited from Codex: the **project** layer loads only once the project is trusted, exactly like `.codex/config.toml`. Until then only the user-scope rules apply.

#### Agent `model` pins are dropped

A catalog agent may pin `model: sonnet` / `opus` / `haiku` in its frontmatter. That pin is **not** written to the generated `.toml`, for both targets (`install` and `migrate`).

Codex's model catalog (`codex debug models`) holds only `gpt-*` slugs, so a Claude alias is unknown to it — and Codex does not reject it. An unknown model is accepted silently, and the session is then assembled *without* the multi-agent instruction blocks, so the subagent quietly loses the collaboration machinery it exists to use. The same happens for a family alias like `gpt-5.6`, which the local catalog does not resolve.

With the key omitted, a Codex agent inherits the parent session's model and reasoning effort — the documented default, and the one that stays correct as OpenAI's catalog moves. If a specific model genuinely matters for an agent, set it in `.codex/config.toml` (`[agents.<name>]`) rather than in the catalog source, so it is not overwritten on regeneration.

#### Rule classes for the Codex target

A catalog rule has no single Codex equivalent. `install` classifies each rule by its frontmatter and dispatches to one of three surfaces:

| Frontmatter | Classification | Output |
|-------------|---------------|--------|
| `always_on: true` | Always-on | Managed block appended to the project-root `AGENTS.md` (Codex always reads the root `AGENTS.md`) |
| `paths:` — non-empty list of directory globs | Path-scoped | Managed block written to `<dir>/AGENTS.md` for each directory in the list; Codex activates it via its root→cwd walk. Glob `src/**` normalises to `src/` |
| Neither field (the default for un-migrated catalog rules) | Description-only | Synthetic Codex-only skill named `rule-<name>` under `.agents/skills/rule-<name>/` (ADR ai-1-2) |

**Classification priority**: a non-empty `paths:` list wins over `always_on: true` — a path-scoped rule is inherently conditional.

Managed `AGENTS.md` blocks are delimited by HTML-comment markers that ai-dotfiles owns:

```
<!-- ai-dotfiles:rule:<name> START -->
<!-- ai-dotfiles:rule:<name> sha256:<hex> -->
<rule body>
<!-- ai-dotfiles:rule:<name> END -->
```

`remove` strips only those markers; surrounding user-authored text in `AGENTS.md` is preserved. An `AGENTS.md` left whitespace-only after the strip is deleted. `install --prune` removes orphaned managed blocks and orphaned `rule-<name>` synthetic skills.

`status` reports:
- `rules/<name> -> AGENTS.md` (or `src/AGENTS.md` etc.) for always-on and path-scoped rules — OK when the managed block is present, NOT INSTALLED otherwise.
- `skills/rule-<name>` for description-only rules — OK / STALE / NOT INSTALLED like any other skill.

The synthetic `rule-<name>` skill is **Codex-only**: a description-only rule also symlinks into `.claude/rules/` for the Claude target as usual. The two are independent.

#### Rule-authoring note

Add `always_on:` or `paths:` to a rule's YAML frontmatter to control where it lands for the Codex target:

```yaml
---
# Rule is always active — lands in the project-root AGENTS.md
always_on: true
---
```

```yaml
---
# Rule applies only inside src/ and tests/ — lands in src/AGENTS.md and tests/AGENTS.md
paths:
  - src/**
  - tests/**
---
```

Without either field the rule becomes a `rule-<name>` skill, which Codex loads on demand via its description (progressive disclosure). This is a sensible default for rules that are not universally relevant.

#### Codex `config.toml` and MCP

Domain `settings.fragment.json` and `mcp.fragment.json` are translated into
`.codex/config.toml` on every `install`, `add`, and `remove`.

**Settings — `[ai_dotfiles]` table**

Keys with a Codex `config.toml` equivalent land in a managed `[ai_dotfiles]`
block, wrapped in marker comments:

```
# >>> ai-dotfiles managed (config) — do not edit by hand >>>
[ai_dotfiles.permissions]
allow = ["Bash(git:*)"]

[ai_dotfiles.sandbox]
network = false
# <<< ai-dotfiles managed (config) <<<
```

Translation rules:

| Fragment key | Codex table | Merge behaviour |
|---|---|---|
| `permissions.allow` / `.deny` / `.ask` | `[ai_dotfiles.permissions]` | Concat-deduped across all installed domains |
| `sandbox` | `[ai_dotfiles.sandbox]` | Last installed domain wins on conflict |
| `hooks` | `.codex/hooks.json` | **Emitted** to Codex's hook harness (a separate file, not config.toml). Twin events translate; events with no Codex twin (`Notification`, `SessionEnd`) are reported. Claude's per-handler `if` command-glob guard is dropped (Codex matches on the tool name via `matcher`), and `$CLAUDE_PROJECT_DIR` → `$CODEX_PROJECT_DIR` |

**MCP — `[mcp_servers]` table**

Each server in a domain's `mcp.fragment.json` lands in a `[mcp_servers.<name>]`
sub-table of `.codex/config.toml`. The Codex `[mcp_servers.<name>]` shape uses
the same keys as the Claude `.mcp.json` shape (`command`, `args`, `env`, `type`,
`url`); keys whose value is `null` are dropped (TOML has no null).

Domain-owned server names are tracked in `.codex/.ai-dotfiles-mcp-ownership.json`
so that `remove` drops only domain-contributed servers and preserves user-authored
entries. A name collision — a domain declaring a server the user already
hand-authored — keeps the user's version and prints a warning.

**Shared file**

The `[ai_dotfiles]` (settings) and `[mcp_servers]` (MCP) regions coexist in
`.codex/config.toml`. Each writer owns exactly one top-level table and leaves all
other content untouched. `remove` rebuilds both regions from the remaining domains
and deletes the file entirely if it would be left empty.

Every generated Codex file starts with:

```
# managed-by: ai-dotfiles
# source-sha256: <hex>
# generator: <n>
```

The hash is of the source catalog file (UTF-8). `ai-dotfiles status` compares it to the current catalog source and flags the artefact as `STALE (source changed)` when they differ.

`generator` is the version of the renderer that produced the file. When ai-dotfiles changes how an artefact is rendered, the *source* is untouched, so the hash alone would report every existing file as fresh forever. A file whose recorded version is behind the current one is flagged `STALE (generator changed)` instead. Either way, `ai-dotfiles install` (or `reconcile`) regenerates.

User-authored files in the same directories (no `# managed-by` header) are never touched by `add`, `remove`, or `--prune`.

`install --prune` also prunes managed Codex artefacts — skills directories and `.toml` files carrying the managed-by header — that are no longer backed by the manifest. Local-origin artefacts (created by `migrate`, recorded in `.codex/.ai-dotfiles-local.json`) are protected from prune.

#### Codex hooks — `.codex/hooks.json`

Domain hooks (from `settings.fragment.json` `hooks`) are translated to Codex's lifecycle-hook harness and written to `.codex/hooks.json` on `install` / `add`, rebuilt/stripped on `remove`. Only events with a Codex twin are emitted; the rest (`Notification`, `SessionEnd`) are reported. Each group keeps its `matcher`; each handler keeps `type` / `command` / `timeout`. Claude's per-handler `if` command-glob guard has no Codex equivalent and is dropped (Codex matches on the tool name via `matcher` — the guard script should self-filter). `$CLAUDE_PROJECT_DIR` is rewritten to `$CODEX_PROJECT_DIR`. Domain groups are ownership-tracked by signature in `.codex/.ai-dotfiles-hooks-ownership.json`, so user-authored project hooks in the same file survive; it coexists with the user-level `~/.codex/hooks.json` (Codex merges hooks additively).

#### Local (non-catalog) elements → Codex

`install` renders only **catalog** elements for Codex. A project's own hand-authored `.claude/` skills/agents/rules — real files, not catalog symlinks, not in the manifest — are carried to Codex by `ai-dotfiles migrate` (see the command reference above):

- **skill** → relative symlink `.agents/skills/<name>` → `../../.claude/skills/<name>` when the raw `SKILL.md` fits Codex's constraints (frontmatter `description` ≤ 1024 chars — a hard cap that fails the whole skill load; valid hyphen-case name); otherwise rendered with the first-sentence trim;
- **agent** → rendered `.codex/agents/<name>.toml`;
- **rule** → synthetic `rule-<name>` skill (description-only / glob) or managed `AGENTS.md` block (always-on / path-scoped);
- **`CLAUDE.md`** → Codex reads it directly via `project_doc_fallback_filenames = ["CLAUDE.md"]` in `.codex/config.toml` (canonical content stays in `CLAUDE.md`; no rendered copy). Codex honours a project-scoped config only once the project is *trusted*;
- **user-authored `.mcp.json` servers** (not domain-owned) → `[mcp_servers]`.

Provenance is recorded in `.codex/.ai-dotfiles-local.json` so `install --prune` keeps these artefacts. `ai-dotfiles reconcile` regenerates any that go stale (an edited local source); `reconcile --check` gates CI. `ai-dotfiles status` lists local elements and whether each has been migrated. Surfaces with no Codex home (`.claude/workflows/`, `.claude/commands/`) are reported by `migrate --dry-run` and `status`, not silently dropped.

### `domain.json`

Every domain has a `catalog/<domain>/domain.json` that declares its metadata:

```json
{
  "name": "python-backend",
  "description": "FastAPI + async SQLAlchemy backend domain",
  "depends": ["@python"],
  "requires": {
    "npm": ["@playwright/mcp"],
    "python": ["click>=8", "pyyaml>=6"],
    "cli": ["gh"]
  }
}
```

All fields are optional. `name` and `description` are informational. `depends` and `requires` are functional — see below. `domain.json` is the single source of truth for domain metadata; `settings.fragment.json` and `mcp.fragment.json` carry only Claude/MCP runtime config (no underscored meta keys).

### Dependencies between elements

A domain declares dependencies via the `depends` field in `domain.json`. Standalone elements (`skill:`, `agent:`, `rule:`) declare them via `depends:` in the YAML frontmatter of the `.md` file:

```yaml
---
name: fastapi-endpoint
depends:
  - "@python-backend"
---
```

Both forms accept the same specifier syntax used in manifests — `@domain`, `skill:name`, `agent:name`, `rule:name`. Cycles are rejected at install time. A missing referenced element is also rejected.

When you `add @python-backend`, the CLI resolves the closure and writes `["@python", "@python-backend"]` to the manifest, in topological order (deps first). The fragment-merge order matches: base layer's permissions/hooks merge first, dependents layer on top.

When you `remove @python` while `@python-backend` is still in the manifest, the CLI refuses with a message listing the dependents. Pass `--force` to break the dependency without removing the dependents, or list the dependents in the same `remove` call.

### `requires` — host-tool packages

`requires` declares packages that must be installed *outside* the catalog (host tooling). Three ecosystems are recognised:

| Ecosystem | What the CLI does on `add` / `install` |
|-----------|----------------------------------------|
| `npm`     | Warns when a listed package is missing from the project's `package.json`. Install with `npm install -D <pkg>`. |
| `python`  | Creates a per-domain venv at `~/.ai-dotfiles/venvs/<domain>/` (via `uv venv` when available, fallback to `python -m venv`) and installs the listed packages into it. The venv is wired up to the domain's `bin/` shims (see below). |
| `cli`     | Probes each name with `which`. Prints a warning when a tool is not on `PATH` — install via your system package manager. |

### `bin/` — domain entry points

A domain may ship executables under `catalog/<domain>/bin/`. On install, the CLI generates one shim per file under `~/.ai-dotfiles/bin/<name>`:

* If `requires.python` is non-empty, the shim execs the per-domain venv's Python on the catalog entry point — so the script's `import click` etc. resolves against the venv, not the system Python.
* Otherwise the shim execs the file directly.
* User-owned files at the shim path are left untouched and a warning is printed.
* Add `~/.ai-dotfiles/bin` to `PATH` once (the CLI prints the export line on first install). After that every domain you install lights up its commands automatically.

`remove`-ing the domain (from the global manifest, or from a project when the domain is not also in `global.json`) drops the shim and the venv.

## Typical workflows

### 1a. New skill → project

```bash
ai-dotfiles create skill my-skill      # scaffold in ~/.ai-dotfiles/catalog/skills/my-skill/
ai-dotfiles add skill:my-skill         # add "skill:my-skill" to ai-dotfiles.json
ai-dotfiles install                    # symlink into <project>/.claude/skills/
```

### 1b. New skill → global (`~/.claude/`)

```bash
ai-dotfiles create skill my-skill      # scaffold in ~/.ai-dotfiles/catalog/skills/my-skill/
ai-dotfiles add -g skill:my-skill      # add "skill:my-skill" to ~/.ai-dotfiles/global.json
                                       # and symlink into ~/.claude/skills/my-skill/
```

To remove from the global manifest:

```bash
ai-dotfiles remove -g skill:my-skill   # drop from global.json + unlink from ~/.claude/
```

The same `-g` flag works for any specifier: `@domain`, `skill:name`, `agent:name`, `rule:name`.

### 1c. New project targeting Claude + Codex

```bash
ai-dotfiles init                           # creates ai-dotfiles.json
# Edit ai-dotfiles.json to add "targets": ["claude", "codex"]
ai-dotfiles add @gitflow skill:commit      # adds to manifest
ai-dotfiles install
# Claude:  <project>/.claude/skills/commit/        (symlink)
#          <project>/.claude/settings.json          (merged from settings.fragment.json)
#          <project>/.mcp.json                      (merged from mcp.fragment.json)
# Codex:   <project>/.agents/skills/commit/        (generated SKILL.md + copied support)
#          <project>/.codex/agents/...toml          (generated from any agent in @gitflow)
#          <project>/.codex/config.toml             (permissions/sandbox from settings.fragment.json;
#                                                    [mcp_servers] from mcp.fragment.json)

ai-dotfiles status                         # includes a "Codex target" block
```

### 2. Vendor an external pack

```bash
ai-dotfiles vendor <vendor> search <query>     # find candidates (where supported)
ai-dotfiles vendor <vendor> install <source>   # fetch into catalog/
ai-dotfiles add skill:<name>                   # or agent:/rule:/@domain; use -g for global
ai-dotfiles install                            # or ai-dotfiles install -g
ai-dotfiles status                             # verify symlinks are healthy
```

Use `ai-dotfiles vendor installed` to audit what vendors contributed, and `ai-dotfiles vendor remove <name>` to drop a vendored entry.

### 3. Bundle several elements as a meta-domain

```bash
ai-dotfiles domain create my-stack         # scaffolds catalog/my-stack/
# Edit catalog/my-stack/domain.json to add:
#   "depends": ["@python", "@gitflow", "skill:code-review"]
ai-dotfiles add @my-stack                  # pulls every dep transitively
```

### 4. Reconcile after a rename or a pull (`--prune`)

When a catalog element is renamed, removed, or restructured — either locally or by someone else whose changes you pulled via `ai-dotfiles pull` — the symlink under `~/.claude/` (or `<project>/.claude/`) keeps pointing at the old path and becomes dangling. Plain `install` creates the *new* symlink but does NOT clean up the old one.

```bash
# On the machine where you renamed / deleted something:
ai-dotfiles install --prune            # project scope
ai-dotfiles install -g --prune         # global scope

# On another machine after pulling:
ai-dotfiles pull
ai-dotfiles install -g --prune         # + install --prune in each project using @gitflow etc.
```

`--prune` only removes symlinks that (a) are symlinks, (b) point into `~/.ai-dotfiles/`, and (c) resolve to a path that no longer exists. User-owned symlinks pointing outside storage and real files are never touched. The default `install` without `--prune` stays conservative (create-only) so accidental invocations can't nuke a stale link you still want.

After pruning, `ai-dotfiles status` should report `All OK`.

### 4. Diagnose broken config

```bash
ai-dotfiles status                     # broken symlinks + settings summary
ai-dotfiles list --available           # cross-check against catalog contents
```

## Notes

- The `targets` field in `ai-dotfiles.json` **and** `global.json` controls which CLIs the manifest renders to. Valid values: `"claude"`, `"codex"`. Absent → `["claude"]`. With `"codex"` in `global.json`, the `-g` commands render into `$CODEX_HOME` (see "What `"codex"` produces at GLOBAL scope").
- The `link_mode` field in `ai-dotfiles.json` controls how the Claude target writes into `.claude/`. Valid values: `"symlink"` (default — live symlinks into the catalog), `"copy"` (real copied files, for native-Windows hosts whose catalog lives in WSL). Absent → `"symlink"`; an unknown value is rejected. A copy is a snapshot — re-run `ai-dotfiles install` after a catalog change. Project-scoped only; `-g` commands always symlink. See [`link_mode`](#link_mode--symlink-vs-copy-for-the-claude-target).
- Never edit `~/.claude/` directly for anything managed by ai-dotfiles — use `add` / `remove` so the manifest stays authoritative.
- The manifest file is `<project>/ai-dotfiles.json` (per-project) or `~/.ai-dotfiles/global.json` (global). Specifiers live under `"packages"`.
- `settings.fragment.json` inside a domain is deep-merged into `.claude/settings.json` on every `add` / `remove` / `install`. **User-authored keys are preserved**: existing settings are loaded as the merge base, then domain fragments are layered on top. `permissions.allow` / `permissions.deny` / `permissions.ask` are concat-deduped (user entries survive, domain entries are appended once). `hooks` keep per-event concat behaviour. Other top-level keys: overlay wins on conflict. Ownership for what ai-dotfiles wrote last time is tracked in `<project>/.claude/.ai-dotfiles-settings-ownership.json`, so `remove` cleans up only entries it added — user lines stay. Caveat: if a user line has the exact same value as a domain entry, the CLI cannot tell them apart and will treat it as managed (i.e. removed on uninstall). **For the Codex target**, the same fragments are also translated into `.codex/config.toml`: `permissions` and `sandbox` land in the managed `[ai_dotfiles]` table; `hooks` are emitted to `.codex/hooks.json` (Codex's hook harness — twin events translate, Claude's per-handler `if` guard is dropped). See [Codex config.toml and MCP](#codex-configtoml-and-mcp).
- `mcp.fragment.json` inside a domain declares `mcpServers` merged into `<project>/.mcp.json` on `add` / `install`. Permissions `mcp__<server>__*` are auto-added to `settings.json` and server names are appended to `enabledMcpjsonServers` (precise allowlist — user-added entries in `.mcp.json` keep Claude Code's default approval prompt). Env-var expansion uses Claude Code's native `${VAR}` / `${VAR:-default}` syntax. Ownership is tracked in `<project>/.claude/.ai-dotfiles-mcp-ownership.json`; user-authored entries in `.mcp.json` are preserved on remove. If you previously denied a server at Claude Code's approval prompt, run `claude mcp reset-project-choices` after `add`. Global scope (`-g`) does not yet support MCP. **For the Codex target**, the same fragments are also translated into the `[mcp_servers]` table of `.codex/config.toml`; ownership is tracked in `.codex/.ai-dotfiles-mcp-ownership.json`. See [Codex config.toml and MCP](#codex-configtoml-and-mcp).
- Do not hand-edit a domain-owned MCP server's entry in `.mcp.json` (e.g. tweaking its `command` or `args`). The ownership file marks it as managed, so the next `add` / `remove` / `install` regenerates it from the domain's fragment and your edits are lost. To change behaviour, edit the catalog's `mcp.fragment.json` (or fork the domain). Only servers that are NOT in the ownership map are considered user-authored and preserved across rebuilds.
- `.gitignore` is auto-managed in a block delimited by `# >>> ai-dotfiles managed — do not edit manually <<<` markers. On every `add` / `remove` / `install` the block is regenerated to list every vendored symlink currently under `.claude/` (format: `/.claude/skills/<name>`). User-authored lines outside the block are never touched; a literal path already ignored by a user-authored line is not duplicated in the block. Opt out per-call with `--no-gitignore`, or globally by setting `"manage_gitignore": false` at the top level of `ai-dotfiles.json` (project) or `~/.ai-dotfiles/global.json` — both must be unset or `true` for the block to be written.
- On conflict or unexpected symlink state, run `ai-dotfiles status` first — do not resolve by deleting files manually.
