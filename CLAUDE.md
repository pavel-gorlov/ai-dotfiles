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

### Codex artefact drift (ADR ai-1-1)

When a catalog agent `.md` changes (body or frontmatter), the generated `.codex/agents/<name>.toml` in any project that targets Codex goes stale. **Regenerate it** by running `ai-dotfiles install` in the affected project.

A generated agent `.toml` carries a `# generator: <n>` header alongside `# source-sha256`. Bump `codex_render.AGENT_GENERATOR_VERSION` whenever you change what `render_agent_toml` emits for an unchanged source — otherwise the source hash still matches and every already-generated project treats its stale artefact as fresh forever. Generator drift is reported as `STALE (generator changed)`.

Agent `model` frontmatter is deliberately **not** rendered into Codex TOML (Claude aliases are unknown to Codex, which accepts them silently and then drops the multi-agent instruction blocks); an omitted key inherits the session model.

`ai-dotfiles status` compares the `# source-sha256` header in each generated file against the current catalog source and reports `STALE (source changed)` for any artefact that needs regeneration — now including always-on/path-scoped rule blocks (sha-compared, not just presence) and `.codex/config.toml` (recomputed from the current fragments). The same drift detection applies to Codex skill `SKILL.md` files generated under `.agents/skills/<name>/`.

**`ai-dotfiles reconcile`** regenerates the stale/missing artefacts in one pass (`reconcile --check` writes nothing and exits non-zero on drift — a CI / pre-commit gate); `ai-dotfiles install` also regenerates. A note in the agent's commit message (e.g. "run `ai-dotfiles reconcile` in projects that use this agent") is the recommended signal to consumers.

### Local elements → Codex (`migrate`)

`install` renders only catalog elements. A project's own hand-authored `.claude/` skills/agents/rules are carried to Codex by **`ai-dotfiles migrate`** (symlink where the format is unchanged, render where it changes; `CLAUDE.md` bridged via `project_doc_fallback_filenames`; domain hooks emitted to `.codex/hooks.json`). Provenance is tracked in `.codex/.ai-dotfiles-local.json` so `install --prune` keeps migrated artefacts. Core modules: `core/local_discovery.py`, `core/codex_migrate.py`, `core/codex_local_registry.py`, `core/codex_reconcile.py`, `core/codex_hooks.py`.

### Global (user-scope) Codex target

`global.json` accepts the same `targets` field as the project manifest (superseding ADR ai-1-3's project-only restriction). With `"targets": ["claude", "codex"]`, `install -g` / `add -g` / `remove -g` / `status -g` / `reconcile -g` also render the global packages into `$CODEX_HOME` (default `~/.codex`; `paths.codex_home()` honours the env var like `storage_root()` honours `AI_DOTFILES_HOME`). Strategy: in-limits catalog skills are **absolute symlinks** into the catalog (gated by `codex_install.skill_symlink_ok` — the 1024-char description cap); over-cap skills and agents render with drift tracking; always-on rules become managed blocks in `$CODEX_HOME/AGENTS.md`; path-scoped rules **demote** to `rule-<name>` skills (no project tree); `~/.claude/CLAUDE.md` is bridged as the reserved managed block `claude-global-instructions` (`core/codex_global.py`). `$CODEX_HOME/config.toml` / `hooks.json` / `AGENTS.md` are user-owned shared files — all writes go through the managed-region / signature-sidecar / marker-block ownership discipline, and the global prune touches exactly three places (`skills/`, `agents/`, `AGENTS.md`), never an `rglob` over `$HOME`. Scope plumbing: `core/codex_layout.py` (`CodexLayout`, `project_layout` / `global_layout`) parameterises `codex_targets` / `codex_config` / `codex_hooks` / `codex_reconcile`.

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
Implementation plan: [tasks/done/implementation-plan.md](tasks/done/implementation-plan.md)
Task details: [tasks/](tasks/)
