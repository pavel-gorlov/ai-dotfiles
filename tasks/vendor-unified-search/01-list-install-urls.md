# Subtask 01: surface install URLs in `vendor list`

Small, self-contained enhancement. Must land before subtask 02 to
avoid merge conflicts on `commands/vendor.py`.

## Goal

`ai-dotfiles vendor list` currently prints `<dep>: +/x` per dependency
cell. Extend so missing deps include their install URL:

```
NAME            DESCRIPTION                                            DEPS
github          Sparse-clone a subtree from GitHub.                    git: +
skills_sh       Install Claude Code skills via the 'skills' npm CLI.   npx: x -> https://nodejs.org/
paks            Install Claude Code skills from the paks registry.    paks: x -> https://paks.stakpak.dev
```

Installed deps stay as `"<name>: +"` (unchanged). Missing deps become
`"<name>: x -> <install_url>"`. Multiple deps still joined by `", "`.

## File scope (exclusive)

- `src/ai_dotfiles/commands/vendor.py` — rewrite the `dep_cells`
  comprehension inside `_meta_list` only
- `tests/e2e/test_vendor_meta.py` — add one new test

## Do NOT touch

- Any vendor module under `src/ai_dotfiles/vendors/`
- `src/ai_dotfiles/vendors/base.py`
- `commands/vendor.py::_deps_check` (already uses this format — leave
  as the reference implementation)
- Any other command file
- `README.md`, `ai-dotfiles-blueprint.md`, scaffolded skill (subtask 03)

## Hard rules

- mypy `--strict` clean; `X | None`; no print; absolute imports
- Reuse `Dependency.install_url` and `Dependency.is_installed()` — no
  new accessors
- Mirror the exact format string from `_deps_check`:
  `"{name}: x -> {install_url}"` (two spaces around `->` in
  `_deps_check`; use two spaces here too for consistency)
- Do not change column headers (`NAME`, `DESCRIPTION`, `DEPS`)

## Implementation sketch

Inside `_meta_list`, replace:
```python
dep_cells = [
    f"{d.name}: {'+' if d.is_installed() else 'x'}" for d in vendor.deps
]
```
with:
```python
dep_cells = [
    f"{d.name}: +" if d.is_installed()
    else f"{d.name}: x  ->  {d.install_url}"
    for d in vendor.deps
]
```

No other changes in the function.

## Acceptance tests

Add to `tests/e2e/test_vendor_meta.py`:

- `test_vendor_list_shows_install_url_for_missing_deps`
  - Monkeypatch `shutil.which` via `ai_dotfiles.vendors.*` so that `git`
    is present and `npx` / `paks` are absent (or use the existing
    pattern from current meta tests).
  - Invoke `vendor list` via `CliRunner`.
  - Assert `"git: +"` appears.
  - Assert `"npx: x  ->  https://nodejs.org/"` appears.
  - Assert `"paks: x  ->  https://paks.stakpak.dev"` appears.
  - Assert exit code is 0.

Do not regress existing `test_vendor_list*` tests — the new format still
contains `"npx: x"` / `"git: +"` substrings so legacy asserts stay
green. Verify by running the suite.

## Definition of Done

1. `poetry run pytest tests/e2e/test_vendor_meta.py -q` — all pass
2. `poetry run pytest -q` — full suite green
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean
7. Manual: `poetry run ai-dotfiles vendor list` shows URLs for any
   missing deps on the local machine

Do NOT commit. Orchestrator runs gates and commits after all subtasks
land.
