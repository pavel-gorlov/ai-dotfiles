# Subtask 03: integration + e2e tests

Exercises the full add/remove/install flow with real filesystem and
`.gitignore` mutations.

## Goal

Prove that:

- `add` writes a managed block listing exactly the symlinks just
  created.
- `remove` shrinks / drops the block appropriately.
- `install` regenerates the block from the current symlink set (so it
  heals from manual edits).
- `--no-gitignore` and `manage_gitignore: false` (project and global)
  each disable the behavior.
- User-authored lines outside the block are preserved across runs.
- Non-git project (no `.git` AND no `.gitignore`) is a silent no-op.

## File scope (exclusive)

- `tests/integration/test_gitignore_sync.py`   (new)
- `tests/e2e/test_gitignore_cli.py`            (new)

## Do NOT touch

- Any source under `src/` — frozen by 01/02.
- Any existing test file.

## Hard rules

- Use `tmp_path`, `monkeypatch` for `HOME` / `AI_DOTFILES_HOME`.
- Mirror fixture patterns from `tests/integration/test_add_remove.py`
  (populated catalog with a synthetic domain). The existing
  `testdomain` shape (skill + agent) is fine.
- `@pytest.mark.integration` on the integration file.
- E2E uses `click.testing.CliRunner` on `add`, `remove`, `install`.

## Tests — `tests/integration/test_gitignore_sync.py`

### add

- `test_add_creates_managed_block_with_linked_paths`
- `test_add_preserves_user_authored_lines_above_and_below`
  (seed `.gitignore` with `node_modules/` and `*.log`, verify both
  survive and sit outside the managed block)
- `test_add_is_idempotent_second_run_does_not_change_file`
- `test_add_skips_when_no_git_and_no_gitignore`
  (no `.git`, no seeded `.gitignore`; after `add` `.gitignore` does
  not exist)
- `test_add_manages_gitignore_when_file_present_without_git`
  (no `.git`, but `.gitignore` exists — we still manage it)
- `test_add_does_not_duplicate_paths_already_in_user_lines`
  (seed `.gitignore` with `/.claude/skills/test-skill`; after `add`
  the managed block omits that path)

### remove

- `test_remove_shrinks_block_to_remaining_symlinks`
- `test_remove_deletes_block_markers_when_no_symlinks_left`
- `test_remove_leaves_user_authored_lines_intact`
- `test_remove_does_not_remove_user_authored_path_that_happens_to_match_symlink`

### install

- `test_install_regenerates_block_from_current_symlinks`
  (delete the managed block by hand, run `install`, block reappears)
- `test_install_prune_updates_block_to_remove_dangling_entries`
  (simulate a renamed catalog entry so the symlink becomes dangling,
  run `install --prune`, assert path is gone from the block)

### opt-out

- `test_no_gitignore_flag_on_add_skips_sync`
- `test_no_gitignore_flag_on_remove_skips_sync`
- `test_no_gitignore_flag_on_install_skips_sync`
- `test_project_manage_gitignore_false_disables_sync`
  (seed `ai-dotfiles.json` with `{"packages": [...], "manage_gitignore":
  false}`)
- `test_global_manage_gitignore_false_disables_sync`
- `test_project_manage_gitignore_true_overrides_global_false`

### global scope

- `test_global_install_never_touches_home_gitignore`
  (`install -g`; `~/.gitignore` / `~/.claude/.gitignore` must not be
  created or modified)

## E2E — `tests/e2e/test_gitignore_cli.py`

- `test_add_then_remove_roundtrip_updates_gitignore` — full `CliRunner`
  flow: `init` → `add @testdomain` → read `.gitignore`, assert block
  contents → `remove @testdomain` → read `.gitignore`, assert markers
  gone but any user lines intact.

## Definition of Done

1. `poetry run pytest -q` — entire suite green.
2. `poetry run mypy src/` — clean.
3. `poetry run ruff check src/ tests/` — clean.
4. `poetry run black --check src/ tests/` — clean.
5. `poetry run pre-commit run --all-files` — clean.

Do NOT commit.
