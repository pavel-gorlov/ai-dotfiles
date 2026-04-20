# ai-dotfiles: Implementation Plan

**Language**: Python >=3.12 with click | **Package manager**: Poetry | **Distribution**: pipx
**Quality**: Ruff + Black + mypy strict | **Commits**: Conventional (commitizen) | **Coverage**: >= 80%

## Architecture

```
src/ai_dotfiles/
├── __init__.py               # __version__
├── __main__.py               # python -m ai_dotfiles
├── cli.py                    # click groups + command registration
├── ui.py                     # colored output helpers (click.secho wrappers)
├── core/
│   ├── errors.py             # CliToolError hierarchy
│   ├── paths.py              # AI_DOTFILES_HOME, project root detection
│   ├── elements.py           # parse @domain, skill:name, etc.
│   ├── manifest.py           # read/write ai-dotfiles.json, global.json
│   ├── symlinks.py           # safe_symlink, backup, chmod +x
│   ├── settings_merge.py     # deep merge settings.fragment.json
│   └── git_ops.py            # git clone, sparse checkout
├── commands/                 # thin wrappers: parse args -> call core -> format output
│   ├── init.py
│   ├── install.py
│   ├── add.py
│   ├── remove.py
│   ├── list_cmd.py
│   ├── status.py
│   ├── vendor.py
│   ├── create_delete.py
│   ├── domain.py
│   └── stack.py
└── scaffold/
    ├── generator.py
    └── templates/            # ~20 template files (package data)

tests/
├── conftest.py               # shared fixtures
├── unit/                     # fast, no I/O, no subprocess
│   ├── test_paths.py
│   ├── test_elements.py
│   ├── test_manifest.py
│   ├── test_settings_merge.py
│   └── test_git_ops.py       # mocked subprocess
├── integration/              # filesystem, symlinks
│   ├── test_symlinks.py
│   ├── test_scaffold.py
│   ├── test_init.py
│   ├── test_install.py
│   └── test_add_remove.py
└── e2e/                      # full CLI via CliRunner
    ├── test_cli.py
    ├── test_list_status.py
    ├── test_create_delete.py
    ├── test_domain.py
    ├── test_stack.py
    └── test_vendor.py
```

### Design principles

- **`commands/`** — thin wrappers: parse args, call `core/`, format output. No business logic.
- **`core/`** — pure logic, testable with unit tests without CLI deps.
- **Error flow**: `core/` raises `CliToolError` subclasses -> `commands/` catches and formats.
- All public functions have type annotations. `mypy --strict` enforced.

## Steps

### Step 0: Dev infrastructure
> [tasks/step-00-infrastructure.md](tasks/step-00-infrastructure.md)

Poetry, pyproject.toml (tool configs), .pre-commit-config.yaml, CI pipeline, .gitignore.
Quality gates must work before any code is written.
**Commit after done.**

### Step 1: Project skeleton
> [tasks/step-01-skeleton.md](tasks/step-01-skeleton.md)

CLI entry point, ui helpers, error hierarchy, test fixtures. Depends on Step 0.
**Commit after done.**

---

### Step 2: Core utilities — 6 PARALLEL agents

| Agent | Task | Details |
|-------|------|---------|
| 2a | `core/paths.py` + tests | [tasks/step-02a-paths.md](tasks/step-02a-paths.md) |
| 2b | `core/elements.py` + tests | [tasks/step-02b-elements.md](tasks/step-02b-elements.md) |
| 2c | `core/manifest.py` + tests | [tasks/step-02c-manifest.md](tasks/step-02c-manifest.md) |
| 2d | `core/symlinks.py` + tests | [tasks/step-02d-symlinks.md](tasks/step-02d-symlinks.md) |
| 2e | `core/settings_merge.py` + tests | [tasks/step-02e-settings-merge.md](tasks/step-02e-settings-merge.md) |
| 2f | `core/git_ops.py` + tests | [tasks/step-02f-git-ops.md](tasks/step-02f-git-ops.md) |

**All 6 run in parallel. Single commit after all complete.**

---

### Step 3: Scaffold templates + generator
> [tasks/step-03-scaffold.md](tasks/step-03-scaffold.md)

~20 template files + generator.py. Depends on Step 2 (uses paths).
**Commit after done.**

---

### Step 4: Command `init` — 1 agent
> [tasks/step-04-init.md](tasks/step-04-init.md)

init, init -g, init -g --from. Depends on Steps 2a, 2c, 2f, 3.
**Commit after done.**

### Step 5: Command `install` — 1 agent
> [tasks/step-05-install.md](tasks/step-05-install.md)

install, install -g. Depends on Steps 2a-2e.
**Commit after done.**

### Step 6: Commands `add` + `remove` — 1 agent
> [tasks/step-06-add-remove.md](tasks/step-06-add-remove.md)

add/remove with -g support. Depends on Steps 2b-2e.
**Commit after done.**

Steps 4, 5, 6 can run in **3 PARALLEL agents** (all depend on Step 2+3, independent of each other).

---

### Step 7: Secondary commands — 5 PARALLEL agents

| Agent | Task | Details |
|-------|------|---------|
| 7a | `commands/list_cmd.py` + test | [tasks/step-07a-list.md](tasks/step-07a-list.md) |
| 7b | `commands/status.py` + test | [tasks/step-07b-status.md](tasks/step-07b-status.md) |
| 7c | `commands/create_delete.py` + test | [tasks/step-07c-create-delete.md](tasks/step-07c-create-delete.md) |
| 7d | `commands/domain.py` + test | [tasks/step-07d-domain.md](tasks/step-07d-domain.md) |
| 7e | `commands/stack.py` + test | [tasks/step-07e-stack.md](tasks/step-07e-stack.md) |

**All 5 run in parallel. Single commit after all complete.**

---

### Step 8: Command `vendor`
> [tasks/step-08-vendor.md](tasks/step-08-vendor.md)

vendor <url> with GitHub URL parsing. Depends on Step 2f.
**Commit after done.**

### Step 9: CLI wiring
> [tasks/step-09-cli-wiring.md](tasks/step-09-cli-wiring.md)

Register all commands, smoke test --help. Depends on Steps 4-8.
**Commit after done.**

### Step 10: README
> [tasks/step-10-readme.md](tasks/step-10-readme.md)

Install, quick start, full command reference.
**Commit after done.**

## Execution graph

```
Step 0 (infrastructure)
  │
  v
Step 1 (skeleton)
  │
  ├─> 2a (paths)       ─┐
  ├─> 2b (elements)    ─┤
  ├─> 2c (manifest)    ─┤ PARALLEL
  ├─> 2d (symlinks)    ─┤
  ├─> 2e (settings)    ─┤
  └─> 2f (git_ops)     ─┘
          │
          v
       Step 3 (scaffold)
          │
  ┌───────┼───────┐
  v       v       v
Step 4  Step 5  Step 6    PARALLEL
  │       │       │
  └───────┼───────┘
          │
  ┌──┬──┬─┼──┐
  v  v  v v  v
 7a 7b 7c 7d 7e          PARALLEL
  │  │  │  │  │
  └──┴──┴──┼──┘
           │
        Step 8
           │
        Step 9
           │
        Step 10
```

## Quality gates (every step)

- `poetry run pytest` — all tests pass
- `poetry run mypy src/` — no type errors
- `poetry run ruff check src/ tests/` — no lint errors
- `poetry run black --check src/ tests/` — formatted

## Verification (final)

```bash
poetry install
ai-dotfiles --version          # 0.1.0
ai-dotfiles --help             # all commands
poetry run pytest --cov --cov-report=term-missing  # >= 80%
poetry run pre-commit run --all-files              # all pass

# Smoke test
ai-dotfiles init -g
ai-dotfiles domain create python
ai-dotfiles create skill test-skill
ai-dotfiles init
ai-dotfiles add @_example skill:git-workflow
ai-dotfiles status
ai-dotfiles list --available
ai-dotfiles remove @_example
```
