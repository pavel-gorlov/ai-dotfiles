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
  rules, hooks, domains) plus `global/` (files linked into `~/.claude/`) and
  `stacks/` (named groups of packages).
- **Symlinks** — `install` / `add` create symlinks from the project's
  `.claude/` into the catalog. The project tree stays tiny; everything lives
  in one place and is versioned once.
- **Settings merge** — each domain may ship a `settings.fragment.json`;
  `ai-dotfiles` deep-merges active fragments into `.claude/settings.json` on
  every `add` / `remove` / `install`.

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
| `list --available`               | List everything available in the catalog and stacks |
| `status`                         | Show symlink health and merged settings summary |

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

### Stacks

| Command | Description |
|---------|-------------|
| `stack create NAME`          | Create an empty `.conf` preset |
| `stack delete NAME`          | Delete a preset |
| `stack list NAME`            | Show items in a preset |
| `stack add NAME ITEMS...`    | Append items (duplicates skipped) |
| `stack remove NAME ITEMS...` | Remove items |
| `stack apply NAME`           | Merge a preset into the current project's manifest |

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
| `vendor list`                                     | Show registered vendors and whether their host dependencies are installed |
| `vendor installed`                                | List every item in the catalog that was added by a vendor (reads `.source`) |
| `vendor remove <name>`                            | Delete a vendored catalog entry by name (no-op for bare `.claude/` symlinks) |
| `vendor github install <url> [--force]`           | Sparse-clone a GitHub subtree into the catalog |
| `vendor github list <url>`                        | List the top-level entries the URL exposes |
| `vendor github deps check \| install [--yes]`     | Check for `git`, or install it on demand |
| `vendor npx_skills install <source> [--force] [--select a,b]` | Install skills via the upstream `skills` npm CLI |
| `vendor npx_skills list <source>`                 | List skills a source exposes |
| `vendor npx_skills find <query>`                  | Search the skills.sh marketplace by keyword |
| `vendor npx_skills deps check \| install [--yes]` | Check for `npx` / Node.js, or install on demand |

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

#### Example: npx skills

```bash
# One-time: install Node.js (npx ships with it)
ai-dotfiles vendor npx_skills deps install

# Search the skills.sh marketplace
ai-dotfiles vendor npx_skills find react

# Enumerate what a specific source exposes
ai-dotfiles vendor npx_skills list vercel-labs/agent-skills

# Install a subset
ai-dotfiles vendor npx_skills install vercel-labs/agent-skills --select deploy-to-vercel
ai-dotfiles add skill:deploy-to-vercel
```

## Storage Structure

```
~/.ai-dotfiles/
├── catalog/
│   ├── <domain>/           # e.g. python/, frontend/
│   │   ├── skills/
│   │   ├── agents/
│   │   ├── rules/
│   │   ├── hooks/
│   │   └── settings.fragment.json
│   ├── skills/<name>/      # standalone skills
│   ├── agents/<name>.md    # standalone agents
│   └── rules/<name>.md     # standalone rules
├── global/                 # files symlinked into ~/.claude/
├── stacks/<name>.conf      # named package presets
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
- Vendor plugins have opt-in runtime dependencies: `vendor github` requires
  `git` on `PATH`; `vendor npx_skills` requires Node.js / `npx`. Install them
  on demand with `ai-dotfiles vendor <vendor> deps install`. The core CLI
  itself has no external runtime dependencies.
- No auto-update for vendored items yet — re-run `vendor <v> install --force`
  to refresh a catalog entry in place.
- `vendor remove <name>` only deletes the catalog entry; if the item is
  already symlinked from an active project or global manifest, first run
  `ai-dotfiles remove <kind>:<name>` to detach the symlinks, then
  `vendor remove`.
- `vendor npx_skills` does not propagate the upstream CLI's rich
  interactive UI to stdout — only the parsed list of skills (for `list`)
  and final placement path (for `install`) are shown.
- `init -g` is not safe to run under `poetry run` with a `HOME` override
  (Poetry itself stores its virtualenvs under the real `$HOME`). To isolate
  the command for testing, either invoke the installed entry point directly
  (e.g. `HOME=$TMP/home ai-dotfiles init -g`) or set `$AI_DOTFILES_HOME`
  only and let `~/.claude/` be re-linked.
- Symlinks only; Windows is not officially supported.

## License

MIT
