# ai-dotfiles

CLI tool for managing Claude Code configuration. Works like a package manager (npm analogy).

## Project

- **Language**: Python >=3.12
- **CLI framework**: click
- **Package manager**: Poetry
- **Entry point**: `ai-dotfiles` -> `src/ai_dotfiles/cli.py:cli`

## Architecture

```
src/ai_dotfiles/
├── cli.py          # click group, command registration only
├── ui.py           # click.secho wrappers (info, success, warn, error)
├── core/           # pure logic, no CLI deps, raises AiDotfilesError
│   ├── errors.py   # exception hierarchy
│   ├── paths.py    # all path resolution
│   ├── elements.py # parse @domain, skill:name, agent:name, rule:name
│   ├── manifest.py # ai-dotfiles.json / global.json CRUD
│   ├── symlinks.py # safe_symlink, backup, chmod +x
│   ├── settings_merge.py  # deep merge settings.fragment.json
│   └── git_ops.py  # git clone, sparse checkout
├── commands/       # thin wrappers: parse args -> call core -> format output
└── scaffold/       # templates + generator for init -g
```

### Key principles

- `commands/` never contains business logic — only arg parsing, calling `core/`, formatting output
- `core/` raises `AiDotfilesError` subclasses; `commands/` catches and formats
- No `print()` — use `ui.info()`, `ui.success()`, `ui.warn()`, `ui.error()`
- All public functions have type annotations (mypy strict)

### Builtin skill sync

The file `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md` is shipped as the `ai-dotfiles` skill inside `catalog/skills/ai-dotfiles/SKILL.md` on `init -g`. It is the user-facing reference for the CLI.

**After every user-visible change to the tool** (new command or subcommand, new/renamed flag, changed specifier syntax, new vendor, changed vendor source format, changed workflow), update this file in the same PR. Keep its command reference, vendor table, and workflows in sync with actual CLI behaviour. If behaviour drifts from the skill, users and Claude operating via the skill will give wrong advice.

## Code style

- **Formatter**: Black (line-length 88)
- **Linter**: Ruff (E, F, I, UP, B, C4, SIM)
- **Types**: mypy --strict
- **Naming**: snake_case functions/vars, PascalCase classes, UPPER_CASE constants
- **Imports**: absolute (`from ai_dotfiles.core.paths import storage_root`)
- **Commits**: conventional commits (feat/fix/refactor/test/docs/chore)

## Commands

```bash
# Dev
poetry install                          # install deps
poetry run pytest                       # run tests
poetry run pytest --cov                 # with coverage (>= 80%)
poetry run mypy src/                    # type check
poetry run ruff check src/ tests/       # lint
poetry run black src/ tests/            # format
poetry run pre-commit run --all-files   # all checks

# Run
ai-dotfiles --version
ai-dotfiles --help
```

## Tests

```
tests/
├── unit/           # fast, no I/O, no subprocess (core/ modules)
├── integration/    # filesystem, symlinks (symlinks, scaffold, init, install)
└── e2e/            # full CLI via click.testing.CliRunner
```

- Use `tmp_path` and fixtures from `conftest.py` — never touch real ~/
- Mock subprocess in unit tests (git_ops)
- Markers: `@pytest.mark.integration`, `@pytest.mark.slow`

## Error hierarchy

```
AiDotfilesError (base)
├── ConfigError    — invalid/missing manifest
├── ElementError   — bad specifier or missing catalog entry
├── LinkError      — symlink operation failed
└── ExternalError  — git clone / subprocess failure
```

## Key paths

- Storage: `~/.ai-dotfiles/` (override: `AI_DOTFILES_HOME` env var)
- Global config: `~/.claude/`
- Project manifest: `<project>/ai-dotfiles.json`
- Project config: `<project>/.claude/`

## Blueprint

Full specification: [ai-dotfiles-blueprint.md](ai-dotfiles-blueprint.md)
Implementation plan: [PLAN.md](PLAN.md)
Task details: [tasks/](tasks/)
