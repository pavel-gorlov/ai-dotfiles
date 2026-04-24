# Subtask 02: wire `sync_gitignore` into add / remove / install + flag

Glue subtask. Imports 01, modifies the three command files + manifest
helper. Must land before 03's integration tests.

## Goal

After every `add` / `remove` / `install` in a project scope, call
`sync_gitignore(project_root, collect_managed_paths(claude_dir, storage))`
— unless the user opted out via `--no-gitignore` flag or a
`manage_gitignore: false` key in the manifest (project > global
precedence).

## File scope (exclusive)

- `src/ai_dotfiles/commands/add.py`
- `src/ai_dotfiles/commands/remove.py`
- `src/ai_dotfiles/commands/install.py`
- `src/ai_dotfiles/core/manifest.py`   (one new helper)

## Do NOT touch

- `core/gitignore.py` — frozen.
- `core/symlinks.py` — reuse existing helpers.
- Any test file — subtask 03 writes tests.

## Hard rules

- mypy `--strict`; no `print`.
- `--no-gitignore` is a Click flag on all three commands. Single
  declaration; wire identically.
- Global opt-out via `manage_gitignore: false` in top-level manifest.
  **Project manifest wins over global** — if project says true, we
  manage; only fall back to global when project doesn't set the key.
- Never run the sync in `-g` / global scope. `~/.claude/` has no
  `.gitignore` to manage.
- Sync is called AFTER all symlinks have been created / removed AND
  AFTER `rebuild_claude_config` runs (so it observes final state).

## `core/manifest.py` — add one helper

```python
def get_flag(path: Path, key: str, default: bool) -> bool:
    """Return a top-level boolean flag from the manifest, or ``default``
    if the key is missing or the manifest doesn't exist."""
```

Do not expand `read_manifest` — just one focused getter.

## `commands/*.py` — wiring pattern

Add a module-level helper in each command file (mirrors existing
`_rebuild_settings` duplication convention):

```python
from ai_dotfiles.core.gitignore import collect_managed_paths, sync_gitignore


def _maybe_sync_gitignore(
    *,
    project_root: Path | None,
    claude_dir: Path,
    manifest_path: Path,
    no_gitignore: bool,
) -> None:
    if project_root is None:          # global scope
        return
    if no_gitignore:
        return
    if not manifest.get_flag(manifest_path, "manage_gitignore", True):
        return
    if not manifest.get_flag(global_manifest_path(), "manage_gitignore", True):
        return
    paths = collect_managed_paths(claude_dir, storage_root())
    sync_gitignore(project_root, paths)
```

Note the precedence: project flag checked FIRST with default True. If
project doesn't disable, global still can. Both default True so the
feature is on by default.

## Click wiring

Add to all three commands:

```python
@click.option(
    "--no-gitignore",
    is_flag=True,
    help="Do not touch .gitignore even if the project manages vendored "
         "symlink paths.",
)
```

Pass through to the helper. For `install`, the flag lives next to
`--prune`.

## Call sites

- `add.py` — at the end of the successful `try:` block, AFTER
  `rebuild_claude_config` / `_rebuild_settings`.
- `remove.py` — same position after `_rebuild_claude_config` branch.
- `install.py` — inside `_install_project` only, AFTER the
  `rebuild_claude_config` call and `_report_pruned`.

## Definition of Done

1. `poetry run pytest -q` — existing suite green.
2. `poetry run mypy src/` — clean.
3. `poetry run ruff check src/ tests/` — clean.
4. `poetry run black --check src/ tests/` — clean.
5. `poetry run pre-commit run --all-files` — clean.
6. Manual: in a throwaway project, run `ai-dotfiles add <existing
   domain>` and inspect `.gitignore` — the managed block exists.
   Then run with `--no-gitignore` in a fresh project — no block.

Do NOT commit.
