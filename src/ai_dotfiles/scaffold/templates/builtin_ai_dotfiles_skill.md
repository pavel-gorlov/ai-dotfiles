---
name: ai-dotfiles
description: Manage Claude Code configuration via the ai-dotfiles CLI — install/add/remove skills, agents, rules, domains and stacks; scaffold new elements; vendor external sources from GitHub, paks or skills.sh; validate symlinks in ~/.claude/.
when_to_use: Trigger when the user mentions "ai-dotfiles", "~/.ai-dotfiles/", "AI_DOTFILES_HOME", "ai-dotfiles.json" or "global.json"; adds/removes/installs/lists a skill, agent, rule, domain or stack for Claude Code; scaffolds a new element; vendors external content (GitHub, paks, npx skills CLI, buildwithclaude, tonsofskills); checks the health of Claude Code symlinks under ~/.claude/ or <project>/.claude/; reconciles ai-dotfiles.json or global.json with the filesystem.
---

# ai-dotfiles

Use this skill when the user asks to install/add/remove Claude Code configuration elements, scaffold new skills/agents/rules, work with domains or stacks, or vendor external sources via the `ai-dotfiles` CLI.

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
- `stack apply|delete|list <TAB>` — existing stack names (`.conf` basenames).
- `stack add <name> <TAB>` — catalog specifiers; `stack remove <name> <TAB>` — items currently in that stack.
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
- `ai-dotfiles list` / `list -g` — show installed packages (project / global).
- `ai-dotfiles list --available` — list everything present in the catalog and stacks.
- `ai-dotfiles status` — report symlink health and a settings summary.

### Elements

- `ai-dotfiles create skill|agent|rule <name>` — scaffold an element in the catalog.
- `ai-dotfiles delete skill|agent|rule <name>` — remove an element from the catalog.
- `ai-dotfiles domain create|delete|list <name>` — manage domains (a folder under `catalog/`).
- `ai-dotfiles domain add|remove <domain> <type> <name>` — manage elements inside a domain.
- `ai-dotfiles stack create|delete|apply <name>` — manage stack presets (`.conf` files merged into the project manifest).

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
```

Cache path for `refresh`-capable vendors: `~/.ai-dotfiles/.vendor-cache/`. `search` / `install` auto-refresh when the cache is older than 24h; pass `--force` to skip the TTL check.

Install ≠ activate. `vendor <name> install` only fetches content into `catalog/`. You still need `ai-dotfiles add [-g] <spec>` + `install` to link it into `.claude/`.

### Specifier syntax

Specifiers are the strings that appear in `packages` arrays:

- `@domain` → `catalog/<domain>/` (whole domain directory).
- `skill:name` → `catalog/skills/<name>/` (directory with `SKILL.md`).
- `agent:name` → `catalog/agents/<name>.md`.
- `rule:name` → `catalog/rules/<name>.md`.

### `domain.json`

Every domain has a `catalog/<domain>/domain.json` that declares its metadata:

```json
{
  "name": "python-backend",
  "description": "FastAPI + async SQLAlchemy backend domain",
  "depends": ["@python"],
  "requires": {
    "npm": ["@playwright/mcp"]
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

`requires` declares packages that must be installed *outside* the catalog (host tooling). Currently only `npm` is recognised: on `add` / `install`, the CLI warns when a package listed in `requires.npm` is missing from the project's `package.json`. Install with `npm install -D <pkg>`.

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

### 2. Vendor an external pack

```bash
ai-dotfiles vendor <vendor> search <query>     # find candidates (where supported)
ai-dotfiles vendor <vendor> install <source>   # fetch into catalog/
ai-dotfiles add skill:<name>                   # or agent:/rule:/@domain; use -g for global
ai-dotfiles install                            # or ai-dotfiles install -g
ai-dotfiles status                             # verify symlinks are healthy
```

Use `ai-dotfiles vendor installed` to audit what vendors contributed, and `ai-dotfiles vendor remove <name>` to drop a vendored entry.

### 3. Apply a stack preset

```bash
ai-dotfiles stack apply <name>         # merge preset into project manifest
ai-dotfiles install
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

- Never edit `~/.claude/` directly for anything managed by ai-dotfiles — use `add` / `remove` so the manifest stays authoritative.
- The manifest file is `<project>/ai-dotfiles.json` (per-project) or `~/.ai-dotfiles/global.json` (global). Specifiers live under `"packages"`.
- `settings.fragment.json` inside a domain is deep-merged into `.claude/settings.json` on every `add` / `remove` / `install`. **User-authored keys are preserved**: existing settings are loaded as the merge base, then domain fragments are layered on top. `permissions.allow` / `permissions.deny` / `permissions.ask` are concat-deduped (user entries survive, domain entries are appended once). `hooks` keep per-event concat behaviour. Other top-level keys: overlay wins on conflict. Ownership for what ai-dotfiles wrote last time is tracked in `<project>/.claude/.ai-dotfiles-settings-ownership.json`, so `remove` cleans up only entries it added — user lines stay. Caveat: if a user line has the exact same value as a domain entry, the CLI cannot tell them apart and will treat it as managed (i.e. removed on uninstall).
- `mcp.fragment.json` inside a domain declares `mcpServers` merged into `<project>/.mcp.json` on `add` / `install`. Permissions `mcp__<server>__*` are auto-added to `settings.json` and server names are appended to `enabledMcpjsonServers` (precise allowlist — user-added entries in `.mcp.json` keep Claude Code's default approval prompt). Env-var expansion uses Claude Code's native `${VAR}` / `${VAR:-default}` syntax. Ownership is tracked in `<project>/.claude/.ai-dotfiles-mcp-ownership.json`; user-authored entries in `.mcp.json` are preserved on remove. If you previously denied a server at Claude Code's approval prompt, run `claude mcp reset-project-choices` after `add`. Global scope (`-g`) does not yet support MCP.
- Do not hand-edit a domain-owned MCP server's entry in `.mcp.json` (e.g. tweaking its `command` or `args`). The ownership file marks it as managed, so the next `add` / `remove` / `install` regenerates it from the domain's fragment and your edits are lost. To change behaviour, edit the catalog's `mcp.fragment.json` (or fork the domain). Only servers that are NOT in the ownership map are considered user-authored and preserved across rebuilds.
- `.gitignore` is auto-managed in a block delimited by `# >>> ai-dotfiles managed — do not edit manually <<<` markers. On every `add` / `remove` / `install` the block is regenerated to list every vendored symlink currently under `.claude/` (format: `/.claude/skills/<name>`). User-authored lines outside the block are never touched; a literal path already ignored by a user-authored line is not duplicated in the block. Opt out per-call with `--no-gitignore`, or globally by setting `"manage_gitignore": false` at the top level of `ai-dotfiles.json` (project) or `~/.ai-dotfiles/global.json` — both must be unset or `true` for the block to be written.
- On conflict or unexpected symlink state, run `ai-dotfiles status` first — do not resolve by deleting files manually.
