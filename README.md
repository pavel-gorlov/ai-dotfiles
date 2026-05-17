# ai-dotfiles

Package manager for Claude Code configuration. Like `npm` for your AI coding setup.

Keep a small `ai-dotfiles.json` in each project, `install` on a new machine, and the
full `.claude/` tree (skills, agents, rules, hooks, settings) is restored from a
single catalog stored under `~/.ai-dotfiles/`.

## Install

Recommended (isolated global install):

```bash
pipx install ai-dotfiles
```

Or from source:

```bash
git clone https://github.com/psgorlov/ai-dotfiles.git
cd ai-dotfiles
poetry install
poetry run ai-dotfiles --help
```

### Enable tab completion (bash / zsh)

```bash
ai-dotfiles completion install          # auto-detects $SHELL
# or: ai-dotfiles completion install --shell bash
# or: ai-dotfiles completion install --shell zsh
```

This writes a completion script to `~/.ai-dotfiles/completions/` and appends a
marker-guarded source block to `~/.bashrc` or `~/.zshrc` (idempotent — safe to
re-run). Restart your shell or `source` the rc file to activate. Use
`--print` to print the script to stdout without touching any files, or
`ai-dotfiles completion uninstall` to remove the block and cached script.

Once installed, **argument values** tab-complete too — package specifiers
for `add`/`remove`, domain names for `domain list/remove`, and so on. The
`-g` flag scopes `add`/`remove` completion to the global vs project
manifest.

## Quick Start

```bash
# 1. Create global storage (~/.ai-dotfiles/) and link ~/.claude/ files
ai-dotfiles init -g

# 2. Author content
ai-dotfiles domain create python           # new domain at catalog/python/
ai-dotfiles create skill code-review       # new standalone skill

# 3. Use it in a project
cd ~/projects/my-api
ai-dotfiles init
ai-dotfiles add @python skill:code-review
ai-dotfiles status                         # show what's linked

# 4. Restore on another machine
ai-dotfiles init -g --from git@github.com:you/my-ai-config.git
cd ~/projects/my-api
ai-dotfiles install
```

## How It Works

- **Manifest** — `ai-dotfiles.json` lists the packages a project uses.
- **Storage** — `~/.ai-dotfiles/` holds the shared `catalog/` (skills, agents,
  rules, hooks, domains) plus `global/` (files linked into `~/.claude/`).
- **Symlinks** — `install` / `add` create symlinks from the project's
  `.claude/` into the catalog. The project tree stays tiny; everything lives
  in one place and is versioned once.
- **Domain manifest** — each domain has a `domain.json` declaring its
  metadata: `name`, `description`, `depends` (other elements it requires)
  and `requires` (host packages, e.g. npm). `ai-dotfiles add @x` resolves
  the `depends` closure transitively and writes everything to the manifest
  in topological order; `remove` blocks if other entries still depend on
  the target (override with `--force`).
- **Multi-target rendering** — the optional `targets` array in `ai-dotfiles.json`
  declares which agent CLIs the manifest renders to. Absent → `["claude"]`, so
  every existing manifest keeps working unchanged. Adding `"codex"` makes
  `install` / `add` / `remove` also render elements for the OpenAI Codex CLI:
  skills land in `.agents/skills/<name>/` (generated `SKILL.md` with a
  first-sentence description, symlinked support files); agents land in
  `.codex/agents/<name>.toml` (generated TOML, committed to the repo). Rules
  dispatch to one of three Codex surfaces depending on their frontmatter (see
  [Codex rule support](#codex-rule-support) below). Domain hooks are skipped
  with an explicit message — Codex has no hook harness.
  The Codex target is **project-scoped only** — `-g` commands always use
  `["claude"]`.
- **Drift detection** — every generated Codex file carries a
  `# managed-by: ai-dotfiles` + `# source-sha256: <hex>` header. The hash is
  of the catalog source file. `ai-dotfiles status` compares it to the current
  source and reports the artefact as `STALE (source changed)` when they
  differ. Run `ai-dotfiles install` to regenerate. User-authored files in the
  same directories (no header) are never touched.
- **Settings merge** — each domain may ship a `settings.fragment.json`
  (pure Claude Code config — no metadata); `ai-dotfiles` deep-merges
  active fragments into `.claude/settings.json` on every `add` / `remove`
  / `install`, in topological order so layered domains compose correctly.
  User-authored keys are preserved (`permissions.allow/deny/ask` are
  concat-deduped with domain entries; hooks concat per event); ownership
  of what ai-dotfiles wrote is tracked so `remove` cleans up only its
  own additions.
- **MCP servers** — domains may also ship `mcp.fragment.json` to declare
  MCP servers; they are merged into `<project>/.mcp.json` on `ai-dotfiles
  add` with `mcp__<server>__*` permissions auto-wired into `settings.json`.
- **Gitignore sync** — the CLI keeps a managed block inside
  `<project>/.gitignore` listing every vendored symlink under `.claude/`,
  so per-machine paths never land in git history. Opt out with
  `--no-gitignore` or `"manage_gitignore": false` in the manifest.

## Multi-target support (Codex CLI)

Add `"targets": ["claude", "codex"]` to `ai-dotfiles.json` to render the same
catalog elements for both Claude Code and OpenAI Codex CLI:

```json
{
  "packages": ["@gitflow", "skill:commit", "agent:reviewer"],
  "targets": ["claude", "codex"]
}
```

Then `ai-dotfiles install` produces:

| Catalog element | Claude Code | Codex CLI |
|-----------------|-------------|-----------|
| `skill:commit` | `.claude/skills/commit/` → symlink | `.agents/skills/commit/` — real dir, generated `SKILL.md` + symlinked support files |
| `agent:reviewer` | `.claude/agents/reviewer.md` → symlink | `.codex/agents/reviewer.toml` — generated TOML |
| `rule:*` / domain `rules/` | `.claude/rules/<name>.md` → symlink | Dispatched by rule frontmatter — see [Codex rule support](#codex-rule-support) |
| Domain `hooks/` | `.claude/settings.json` hooks | Skipped (explicit message) — Codex has no hook harness |
| Domain `settings.fragment.json` | Deep-merged into `.claude/settings.json` | `permissions` and `sandbox` keys land in the managed `[ai_dotfiles]` table of `.codex/config.toml`; `hooks` is skipped with an explicit message |
| Domain `mcp.fragment.json` | Merged into `<project>/.mcp.json` | Servers land in the `[mcp_servers]` table of `.codex/config.toml`; ownership tracked in `.codex/.ai-dotfiles-mcp-ownership.json` |

Every generated Codex file carries `# managed-by: ai-dotfiles` and
`# source-sha256: <hex>` (hash of the source catalog file). `ai-dotfiles status`
reports `STALE (source changed)` when the source changes; `ai-dotfiles install`
regenerates the file. User-authored files in the same directories are never
touched.

`install --prune` also removes managed Codex artefacts no longer in the manifest.

The Codex target is **project-scoped only** — `install -g`, `add -g`, `remove -g`,
and `status -g` always target Claude Code (`["claude"]`). The global manifest
has no `targets` field.

## Copy mode for the Claude target (`link_mode`)

By default the Claude target writes `.claude/skills/`, `.claude/agents/` and
`.claude/rules/` as **symlinks** into `~/.ai-dotfiles/catalog/` — a live view of
the catalog. On Linux and WSL that is the right choice.

It breaks on a **native-Windows host whose catalog lives in WSL**: native Windows
cannot resolve a symlink that points into the WSL filesystem, so every `.claude/`
entry appears broken / 0-byte to a native-Windows Claude Code.

Set `link_mode` in `ai-dotfiles.json` to opt into copying real files instead:

```json
{
  "packages": ["@gitflow", "skill:commit"],
  "link_mode": "copy"
}
```

| `link_mode` | Behaviour |
|-------------|-----------|
| `"symlink"` | Default. `.claude/` entries are symlinks into the catalog. |
| `"copy"` | `.claude/` entries are real copied files — fully self-contained, resolvable by any host. |

An absent `link_mode` field resolves to `"symlink"`, so every existing manifest
keeps byte-identical behaviour; an unknown value is rejected.

A copy is a **snapshot**, not a live view — unlike a symlink it does not track the
catalog. After a catalog change (a `pull`, an edit, a vendored update) re-run
`ai-dotfiles install` to refresh the copies. `remove` and `install --prune` clean
up stale copies; a `.ai-dotfiles-copies.json` sidecar under `.claude/` records
which entries are ai-dotfiles-managed, so user-authored files are never deleted.
`ai-dotfiles status` reports copies as `OK (copied)`.

`link_mode` is **project-scoped only** — `-g` commands always symlink, since the
global `~/.claude/` sits next to the catalog.

### Codex rule support

A catalog rule has no single Codex equivalent. `install` reads two optional
frontmatter fields on each rule file and dispatches to one of three surfaces:

| Rule frontmatter | Classification | Codex output |
|-----------------|---------------|--------------|
| `always_on: true` | Always-on | Managed block in the project-root `AGENTS.md` |
| `paths: [src/**, tests/**]` | Path-scoped | Managed block in `src/AGENTS.md` and `tests/AGENTS.md`; Codex activates it via its root→cwd walk |
| Neither field (default) | Description-only | Synthetic Codex-only skill `rule-<name>` under `.agents/skills/rule-<name>/` |

**Classification priority**: `paths:` wins over `always_on:` when both are set.

`AGENTS.md` blocks are owned by ai-dotfiles via HTML-comment markers
(`<!-- ai-dotfiles:rule:<name> START/END -->`). `remove` strips only those
markers; user-authored text in `AGENTS.md` is preserved. An `AGENTS.md` left
empty after the strip is deleted. `install --prune` removes orphaned blocks and
orphaned `rule-<name>` skills.

`ai-dotfiles status` reports the block presence for always-on / path-scoped
rules (`rules/<name> -> AGENTS.md`) and drift for description-only rule skills
(`skills/rule-<name>`).

The synthetic `rule-<name>` skill is **Codex-only**: the same rule still
symlinks into `.claude/rules/` for the Claude target.

To control where a rule lands for Codex, add `always_on:` or `paths:` to its
YAML frontmatter:

```yaml
---
always_on: true   # always active — lands in the project-root AGENTS.md
---
```

```yaml
---
paths:            # conditional — lands in src/AGENTS.md and tests/AGENTS.md
  - src/**
  - tests/**
---
```

Without either field the rule becomes a `rule-<name>` skill (Codex loads it on
demand via its description). This is the default for any existing catalog rule
that has not yet been migrated.

### Codex config.toml and MCP support

Domain `settings.fragment.json` and `mcp.fragment.json` are translated into
`.codex/config.toml` by `install`, `add`, and `remove`.

**Settings — `[ai_dotfiles]` table**

Keys with a Codex `config.toml` equivalent land in the `[ai_dotfiles]` managed
table, wrapped in marker comments so the region is clearly owned:

```toml
# >>> ai-dotfiles managed (config) — do not edit by hand >>>
[ai_dotfiles.permissions]
allow = ["Bash(git:*)"]
deny = []

[ai_dotfiles.sandbox]
network = false
# <<< ai-dotfiles managed (config) <<<
```

- `permissions` — the `allow` / `deny` / `ask` lists from the fragment land
  under `[ai_dotfiles.permissions]`, concat-deduped across all installed domains.
- `sandbox` — the fragment's `sandbox` object lands under `[ai_dotfiles.sandbox]`
  (last installed domain wins on conflict).
- `hooks` — Codex has no hook harness. Hooks are **not** written; the CLI prints
  an explicit skip message naming each domain whose fragment contained hooks.

**MCP — `[mcp_servers]` table**

Each server declared in a domain's `mcp.fragment.json` is written as a
`[mcp_servers.<name>]` sub-table in `.codex/config.toml`. The Codex
`[mcp_servers.<name>]` shape uses the same keys as the Claude `.mcp.json` shape
(`command`, `args`, `env`, `type`, `url`); the only difference is the container
format. Keys with a `null` value are dropped (TOML has no null).

Domain-owned server names are tracked in `.codex/.ai-dotfiles-mcp-ownership.json`
so that `remove` strips only domain-contributed servers. User-authored entries in
`[mcp_servers]` are preserved across every `add`, `remove`, and `install`. A name
collision — where a domain declares a server name the user already hand-authored —
keeps the user's version and prints a warning.

**Shared file**

The `[ai_dotfiles]` (settings) and `[mcp_servers]` (MCP) regions coexist in
`.codex/config.toml`. Each writer touches only its own top-level table; all other
tables, including user-authored ones, survive untouched.

`remove` rebuilds both regions from the remaining installed domains, and deletes
the file entirely if it would be left empty.

## Element Format

Packages in the manifest use these shapes:

| Format        | Resolves to                    |
|---------------|--------------------------------|
| `@domain`     | `catalog/<domain>/`            |
| `skill:name`  | `catalog/skills/<name>/`       |
| `agent:name`  | `catalog/agents/<name>.md`     |
| `rule:name`   | `catalog/rules/<name>.md`      |

A domain bundles any combination of skills, agents, rules and hooks under one
name. Standalone elements (`skill:`, `agent:`, `rule:`) live at the top level
of the catalog and can be added individually.

## Commands

Run `ai-dotfiles <command> --help` for full options.

### Project / global

| Command | Description |
|---------|-------------|
| `init`                           | Create `ai-dotfiles.json` in the current project |
| `init -g`                        | Create global storage at `~/.ai-dotfiles/` and link `~/.claude/` |
| `init -g --from <git-url>`       | Clone an existing storage repo into `~/.ai-dotfiles/` |
| `add PACKAGES...`                | Add packages to the manifest and symlink them |
| `remove PACKAGES...`             | Remove packages from the manifest and unlink them |
| `install`                        | Recreate symlinks from the project manifest |
| `install -g`                     | Recreate symlinks from the global manifest |
| `list`                           | List installed packages (project) |
| `list -g`                        | List installed packages (global) |
| `list --available`               | List everything available in the catalog |
| `status`                         | Show symlink health and merged settings summary |
| `update`                         | Refresh CLI-managed files inside storage (today: the built-in `ai-dotfiles` skill) |
| `completion install [--shell bash\|zsh] [--print]` | Install tab completion into `~/.bashrc` / `~/.zshrc` (auto-detects shell from `$SHELL`) |
| `completion uninstall [--shell bash\|zsh]` | Remove the completion block and delete the cached script |

### Elements

| Command | Description |
|---------|-------------|
| `create skill\|agent\|rule NAME` | Scaffold a standalone element in `catalog/` |
| `delete skill\|agent\|rule NAME` | Remove a standalone element from `catalog/` |

### Domains

| Command | Description |
|---------|-------------|
| `domain create NAME`                         | Create an empty domain at `catalog/<NAME>/` |
| `domain delete NAME`                         | Delete the domain directory |
| `domain list NAME`                           | List contents of a domain |
| `domain add NAME ELEMENT_TYPE ELEMENT_NAME`  | Scaffold an element inside a domain |
| `domain remove NAME ELEMENT_TYPE NAME`       | Remove an element from a domain |

> Need an opinionated bundle of several elements? Create a meta-domain:
> `ai-dotfiles domain create my-stack`, edit its `domain.json` to list
> `depends: ["@python", "@gitflow", "skill:code-review"]`, then
> `ai-dotfiles add @my-stack`. The transitive closure is pulled in for
> you. There is no separate `stack` command.

### Vendoring

Third-party skills, agents and rules are fetched through named vendor
plugins. Each vendor knows how to talk to one source (GitHub, the
`skills` npm CLI, ...) and drops the result into the shared
`catalog/`. The command tree is built dynamically from the vendor
registry, so `vendor --help` always lists every vendor currently
available.

#### Command tree

| Command | Description |
|---------|-------------|
| `vendor list`                                     | Registered vendors + dependency status (with install URL for any missing dep). |
| `vendor installed`                                | List every item in the catalog that was added by a vendor (reads `.source`) |
| `vendor remove <name>`                            | Delete a vendored catalog entry by name (no-op for bare `.claude/` symlinks) |
| `vendor search <query> [-v NAME ...] [--limit N]` | Aggregated search across every vendor whose deps are installed; results grouped by vendor. |
| `vendor github install <url> [--force]`           | Sparse-clone a GitHub subtree into the catalog |
| `vendor github list <url>`                        | List the top-level entries the URL exposes |
| `vendor github deps check`                        | Check that `git` is on `PATH` |
| `vendor skills_sh install <source> [--force] [--select a,b]` | Install skills via the upstream `skills` npm CLI |
| `vendor skills_sh list <source>`                  | List skills a source exposes |
| `vendor skills_sh search <query>`                 | Search the skills.sh marketplace by keyword |
| `vendor skills_sh deps check`                     | Check that `npx` / Node.js is on `PATH` |
| `vendor paks install <source> [--force]`          | Install a skill from the paks registry |
| `vendor paks list <source>`                       | Echo the source back (paks models one source as one skill) |
| `vendor paks search <query>`                      | Search the paks registry by keyword |
| `vendor paks deps check`                          | Check that the `paks` binary is on `PATH` |
| `vendor buildwithclaude install <name> [--force]` | Install a skill from the buildwithclaude catalog |
| `vendor buildwithclaude list <name>`              | Echo the skill name back |
| `vendor buildwithclaude search <query>`           | Search the cached buildwithclaude catalog by keyword |
| `vendor buildwithclaude refresh [--force]`        | Re-fetch the catalog cache (24h TTL) |
| `vendor buildwithclaude deps check`               | Check that `git` is on `PATH` |
| `vendor tonsofskills install <name> [--force]`    | Install a skill from the tonsofskills catalog |
| `vendor tonsofskills list <name>`                 | Echo the skill name back |
| `vendor tonsofskills search <query>`              | Search the cached tonsofskills catalog by keyword |
| `vendor tonsofskills refresh [--force]`           | Re-fetch the catalog cache (24h TTL) |
| `vendor tonsofskills deps check`                  | Check that `git` is on `PATH` |

After a successful `install`, the item is written to
`catalog/<kind>s/<name>/` alongside a `.source` file recording the
vendor, origin, fetch date and detected license. The CLI prints the
`ai-dotfiles add` command needed to link it into a project or global
manifest.

#### Example: GitHub

```bash
ai-dotfiles vendor github install \
  https://github.com/anthropics/skills/tree/main/skills/pdf
ai-dotfiles add skill:pdf
```

`vendor github` accepts either a repo root URL or a `/tree/<branch>/<subpath>`
URL; the element kind (skill/agent/rule) is auto-detected from the
fetched content.

#### Example: skills.sh

```bash
# One-time: install Node.js so `npx` is on PATH (https://nodejs.org/)
ai-dotfiles vendor skills_sh deps check

# Search the skills.sh marketplace
ai-dotfiles vendor skills_sh search react

# Enumerate what a specific source exposes
ai-dotfiles vendor skills_sh list vercel-labs/agent-skills

# Install a subset
ai-dotfiles vendor skills_sh install vercel-labs/agent-skills --select deploy-to-vercel
ai-dotfiles add skill:deploy-to-vercel
```

#### Example: paks

```bash
# One-time: install paks (https://paks.stakpak.dev)
brew tap stakpak/stakpak && brew install paks

# Check it's wired up
ai-dotfiles vendor paks deps check

# Search the paks registry
ai-dotfiles vendor paks search kubernetes

# Install one skill (paks = one source, one skill)
ai-dotfiles vendor paks install kubernetes-deploy
ai-dotfiles add skill:kubernetes-deploy
```

#### Example: buildwithclaude

```bash
# One-off: prime the catalog cache (git clone, ~1 min)
ai-dotfiles vendor buildwithclaude refresh

# Search the cached catalog
ai-dotfiles vendor buildwithclaude search typescript

# Install one skill
ai-dotfiles vendor buildwithclaude install mcp-builder
ai-dotfiles add skill:mcp-builder
```

The catalog is mirrored under `~/.ai-dotfiles/.vendor-cache/` with a
24h TTL; `search`/`install` auto-refresh when stale, or you can force
it with `vendor buildwithclaude refresh --force`.

#### Example: tonsofskills

```bash
ai-dotfiles vendor tonsofskills refresh   # slow first time: 20k files
ai-dotfiles vendor tonsofskills search kubernetes
ai-dotfiles vendor tonsofskills install generating-database-seed-data
ai-dotfiles add skill:generating-database-seed-data
```

The upstream repo keeps a large `backups/` tree of historical
snapshots; the vendor scans only the live `plugins/` subtree, so
search results map to the actual curated catalog.

#### Example: aggregated search

```bash
ai-dotfiles vendor list              # see which vendors are ready
ai-dotfiles vendor search git        # query every active vendor
ai-dotfiles vendor search git --limit 5
ai-dotfiles vendor search git -v buildwithclaude -v tonsofskills
```

Vendors with missing deps are shown as `skipped (deps missing: ...)`
with the install URL. Vendors without a `search` capability (e.g.
`github`) are omitted silently.

## Storage Structure

```
~/.ai-dotfiles/
├── catalog/
│   ├── <domain>/           # e.g. python/, frontend/
│   │   ├── domain.json              # name, description, depends, requires
│   │   ├── settings.fragment.json   # Claude Code config (optional)
│   │   ├── mcp.fragment.json        # MCP servers (optional)
│   │   ├── skills/
│   │   ├── agents/
│   │   ├── rules/
│   │   └── hooks/
│   ├── skills/<name>/      # standalone skills
│   ├── agents/<name>.md    # standalone agents
│   └── rules/<name>.md     # standalone rules
├── global/                 # files symlinked into ~/.claude/
└── global.json             # manifest for ~/.claude/
```

## Configuration

| Setting          | Value              |
|------------------|--------------------|
| Storage path     | `~/.ai-dotfiles/`  |
| Override         | `AI_DOTFILES_HOME` |
| Project manifest | `ai-dotfiles.json` |
| Global manifest  | `~/.ai-dotfiles/global.json` |
| Project config   | `<project>/.claude/` |
| Global config    | `~/.claude/` |

Set `AI_DOTFILES_HOME` to relocate the storage root (useful for testing or
isolating multiple configurations).

## Development

```bash
poetry install
poetry run pytest                       # full test suite
poetry run pytest --cov                 # with coverage (>= 80% required)
poetry run mypy src/                    # type check (strict)
poetry run ruff check src/ tests/       # lint
poetry run black src/ tests/            # format
poetry run pre-commit run --all-files   # everything at once
```

### Install the dev version on `PATH`

Expose the working tree as a global `ai-dotfiles` command — edits under `src/`
are picked up without reinstalling.

With `uv`:

```bash
uv tool install --editable .
# uninstall: uv tool uninstall ai-dotfiles
```

With `pipx`:

```bash
pipx install --editable .
# uninstall: pipx uninstall ai-dotfiles
```

Both place the entry point in `~/.local/bin/ai-dotfiles`; make sure that
directory is on your `PATH`.

Conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
are enforced via `commitizen`.

## Known limitations

- `init -g --from` clones the storage repo but does not verify its layout; an
  unrelated repo will be accepted and may produce confusing errors on first
  `install`.
- Vendor plugins have opt-in runtime dependencies: `vendor github`,
  `vendor buildwithclaude`, `vendor tonsofskills` need `git` on `PATH`;
  `vendor skills_sh` needs Node.js / `npx`; `vendor paks` needs the
  `paks` binary. Install them manually following the URL printed by
  `ai-dotfiles vendor <vendor> deps check`; the core CLI itself has no
  external runtime dependencies.
- Marketplace-backed vendors (`buildwithclaude`, `tonsofskills`) keep a
  local catalog mirror under `~/.ai-dotfiles/.vendor-cache/` (24h TTL).
  `rm -rf ~/.ai-dotfiles/.vendor-cache/` is safe to free disk.
- Offline mode works against the last successful `refresh`; if the
  cache is empty and the machine is offline, `search`/`install` fail
  with a git-error.
- Plugin-level extras (hooks, agents bundled in plugins) are not
  imported by the marketplace vendors — we extract `SKILL.md`
  directories only.
- No auto-update for vendored items yet — re-run `vendor <v> install --force`
  to refresh a catalog entry in place.
- `vendor remove <name>` only deletes the catalog entry; if the item is
  already symlinked from an active project or global manifest, first run
  `ai-dotfiles remove <kind>:<name>` to detach the symlinks, then
  `vendor remove`.
- `vendor skills_sh` does not propagate the upstream CLI's rich
  interactive UI to stdout — only the parsed list of skills (for `list`)
  and final placement path (for `install`) are shown.
- `init -g` is not safe to run under `poetry run` with a `HOME` override
  (Poetry itself stores its virtualenvs under the real `$HOME`). To isolate
  the command for testing, either invoke the installed entry point directly
  (e.g. `HOME=$TMP/home ai-dotfiles init -g`) or set `$AI_DOTFILES_HOME`
  only and let `~/.claude/` be re-linked.
- The Claude target uses symlinks by default. On a native-Windows host whose
  catalog lives in WSL, set `"link_mode": "copy"` in `ai-dotfiles.json` so
  `.claude/` holds real copied files instead — see
  [Copy mode for the Claude target](#copy-mode-for-the-claude-target-link_mode).
- Codex target: domain `hooks/` members are not rendered for Codex — the
  command prints an explicit skip message (Codex has no hook harness). Rules
  are rendered (see [Codex rule support](#codex-rule-support)).
- Codex target: `install -g`, `add -g`, `remove -g` always target Claude Code
  only; the global manifest has no `targets` field and does not support the
  Codex target.

## License

MIT
