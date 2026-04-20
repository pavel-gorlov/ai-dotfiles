# Vendor V4: rewrite vendor CLI as click group

Replace the flat `vendor <url>` command with a click Group that builds
subcommands dynamically from the vendor registry. Wire both vendors
(github + npx_skills) into `REGISTRY`. Implement meta subcommands.

## Goal

After this task:

```
ai-dotfiles vendor list
ai-dotfiles vendor installed
ai-dotfiles vendor remove <name>
ai-dotfiles vendor github install <url> [--force]
ai-dotfiles vendor github list <url>
ai-dotfiles vendor github deps check
ai-dotfiles vendor github deps install [--yes]
ai-dotfiles vendor npx_skills install <source> [--force] [--select s1,s2]
ai-dotfiles vendor npx_skills list <source>
ai-dotfiles vendor npx_skills deps check
ai-dotfiles vendor npx_skills deps install [--yes]
```

Old flat `ai-dotfiles vendor <url>` is removed (no shim).

## File scope (exclusive)

- `src/ai_dotfiles/commands/vendor.py` — REWRITTEN as click Group that
  dynamically builds per-vendor subcommand groups from `REGISTRY`
- `src/ai_dotfiles/vendors/__init__.py` — populate `REGISTRY` with
  `"github": GITHUB` and `"npx_skills": NPX_SKILLS` (import from the
  two vendor modules)
- `src/ai_dotfiles/cli.py` — 1-line change if needed (import stays the
  same since vendor is already registered; verify `cli.add_command(vendor)`
  still points at the new group object)
- `tests/e2e/test_cli.py` — update parametrized help-test list: replace
  `"vendor"` entry with entries that cover the group (`vendor`,
  `vendor github`, `vendor npx_skills`); add smoke tests for `vendor
  list`, `vendor installed`, `vendor remove`
- `tests/e2e/test_vendor.py` — DELETE (old tests are replaced by
  V2/V3 direct-vendor tests and new CLI smoke tests here)
- `tests/e2e/test_vendor_meta.py` (new) — tests for `vendor list`,
  `vendor installed`, `vendor remove`

## Do NOT touch

- `vendors/base.py`, `source_file.py`, `placement.py`, `deps.py`,
  `github.py`, `npx_skills.py`
- `core/**`
- Other command files

## Command details

### `vendor list`

Prints `REGISTRY` contents as a table:
```
NAME          DESCRIPTION                                          DEPS
github        Sparse-clone a subtree from GitHub.                  git: +
npx_skills    Install Claude Code skills via the 'skills' npm CLI. npx: x
```

Use `+` if dep installed, `x` if missing. Exit 0.

### `vendor installed`

Scans `catalog/**/*` for `.source` files via `vendors.source_file.read`
and prints one row per vendored item:
```
NAME           KIND     VENDOR       ORIGIN                         FETCHED
awesome-skill  skill    github       github:org/awesome-skills      2026-04-16
oneshot        skill    npx_skills   npx:skills:vercel-labs/skills  2026-04-16
```

Sort by kind, then name. Empty output + "No vendored items." if nothing.

### `vendor remove <name>`

Finds `catalog/**/<name>/.source` (by walking catalog). If found:
- Warn if referenced in any manifest / stack (reuse the `find_usage`
  helper from `commands/create_delete.py` if it's module-level; if not,
  inline the scan)
- Confirm (unless `--yes`)
- `shutil.rmtree(catalog_dir_of_item)`
- Print `Removed <relpath>`

If not found → `ElementError`.
If multiple matches (same name in agents/ and skills/) → print list, ask
user to disambiguate via `--kind`.

### Per-vendor subgroup (built dynamically)

For each `(name, vendor)` in `REGISTRY`, construct a `click.Group(name)`
with commands `install`, `list`, `deps`. The `deps` is itself a subgroup
with `check` and `install` subcommands.

```
@vendor.group(name="github")
def _github(): ...
```

Implementation note: build the groups in a helper function; use
`@vendor.group()` programmatically via `click.Group.add_command(group)`
so we don't need decorators at module scope. Keep this loop tight (<30
LOC).

### `vendor <v> install <source>`

1. `deps.ensure(vendor)` — raises if missing
2. `with tempfile.TemporaryDirectory() as work:`
   - `items = vendor.fetch(source, select=..., workdir=Path(work))`
3. For each item: `place_item(item, catalog_root=catalog_dir(), force=force, vendor_name=vendor.name)`
4. Summary: per-item `ui.success("Installed catalog/{kind}s/{name}/")`
   and final "Ready to use: ai-dotfiles add skill:<name>" hint

`--select "a,b,c"` → tuple parsed from comma-split, whitespace stripped,
empty entries rejected.

### `vendor <v> list <source>`

1. `deps.ensure(vendor)`
2. `for name in vendor.list_source(source): click.echo(name)`

### `vendor <v> deps check`

Prints each dep and status `+ installed` / `x missing`. Exit 0 if all
installed, 1 if any missing.

### `vendor <v> deps install [--yes]`

Calls `deps.install(vendor, yes=yes)`.

## Acceptance tests

Top-level (`test_cli.py`):
- `ai-dotfiles vendor --help` lists `github`, `npx_skills`, `list`,
  `installed`, `remove`
- `ai-dotfiles vendor github --help` lists `install`, `list`, `deps`
- `ai-dotfiles vendor npx_skills --help` lists `install`, `list`, `deps`
- `ai-dotfiles vendor github deps --help` lists `check`, `install`

Meta (`test_vendor_meta.py`, all via `CliRunner`):
- `vendor list` — rows for both vendors; deps status reflects
  monkeypatched `shutil.which`
- `vendor installed` on empty catalog → "No vendored items."
- `vendor installed` after placing a fake `.source` via direct file
  write under `tmp_storage/catalog/skills/foo/` → shows foo
- `vendor remove foo` — deletes catalog/skills/foo/ + warns if in a
  manifest or stack
- `vendor remove nonexistent` → ElementError
- `vendor github install <url>` happy path (mock `GITHUB.fetch`) →
  catalog/skills/<name>/.source exists
- `vendor github install <url>` + existing dest, no `--force` →
  ElementError
- `vendor github install <url>` + `--force` → overwrites
- `vendor github list <url>` — prints names
- `vendor github deps check` — exits 0 when git present, 1 when absent
- `vendor npx_skills install <src>` happy path with mocked subprocess
- `vendor npx_skills deps check` — exits 1 when npx missing

## Hard rules

- mypy --strict, `X | None`, no print, absolute imports
- `commands/vendor.py` stays a thin CLI layer — all logic delegates to
  `vendors/**` + `core/**`
- Reuse `ai_dotfiles.ui.*`, `ai_dotfiles.core.errors.*`, `ai_dotfiles.core.paths.*`

## Definition of Done

1. `poetry run pytest tests/e2e/test_cli.py tests/e2e/test_vendor_meta.py -q` — all pass
2. Full suite: `poetry run pytest -q` — green (261 was baseline; now
   subtracting old test_vendor.py (~8 cases), adding new meta tests)
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean
7. Manual CLI: `poetry run ai-dotfiles vendor --help` shows the new tree

Do NOT commit.
