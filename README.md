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

| Command | Description |
|---------|-------------|
| `vendor URL`       | Download a GitHub subtree into `catalog/` (auto-detects element type) |
| `vendor -f URL`    | Overwrite the destination if it already exists |

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

Conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
are enforced via `commitizen`.

## Known limitations

- `init -g --from` clones the storage repo but does not verify its layout; an
  unrelated repo will be accepted and may produce confusing errors on first
  `install`.
- `vendor` uses git sparse-checkout and requires a working `git` on `PATH`.
- Symlinks only; Windows is not officially supported.

## License

MIT
