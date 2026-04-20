# Vendor V2: migrate GitHub vendor

Move the existing GitHub sparse-clone logic from `commands/vendor.py` into
`vendors/github.py` conforming to the `Vendor` protocol from V1. Adapt
existing tests accordingly. Do not change behavior.

## Goal

`vendors/github.py` exposes a `GITHUB: Vendor` object (module-level
instance) that implements:
- `name = "github"`
- `display_name = "GitHub"`
- `description = "Sparse-clone a subtree from GitHub."`
- `deps = (Dependency(name="git", ...),)` — git presence via `shutil.which("git")`
- `list_source(url)` — returns top-level entries under the URL's subpath
  (use `git ls-tree -r --name-only` after a shallow no-checkout clone, or
  simpler: sparse-checkout + filesystem scan)
- `fetch(url, *, select, workdir)`:
  - Reuses `core.git_ops.parse_github_url` and `git_sparse_checkout`
  - Produces exactly one `FetchedItem` matching current behavior: kind
    inferred by `core.git_ops.detect_element_type` (default "skill"),
    name derived from URL, `origin=f"github:{owner}/{repo}[/subpath]"`,
    license detected from LICENSE* at the fetched directory root.
  - If `select` is non-empty, raise `ElementError("GitHub vendor does
    not support --select; use a more specific URL")` — keep scope tight.

## File scope (exclusive)

- `src/ai_dotfiles/vendors/github.py` (new)
- Tests to add/modify:
  - `tests/e2e/test_vendor_github.py` (new — copy GitHub-relevant cases
    from old `tests/e2e/test_vendor.py` and adapt to direct
    `github.fetch(...)` call via the Vendor protocol, since V2 runs
    before V4 rewires the CLI)

## Do NOT touch

- `src/ai_dotfiles/commands/vendor.py` — leave the old CLI intact until V4
  replaces it. Old `tests/e2e/test_vendor.py` stays green (it drives the
  old CLI) until V4 deletes it.
- `src/ai_dotfiles/vendors/__init__.py` — do NOT add GitHub to REGISTRY
  here. V4 handles registry wiring in one place.
- `core/git_ops.py` — unchanged

## Hard rules

- mypy --strict, `X | None`, no print, absolute imports
- Reuse `core.git_ops` for subprocess / URL parsing
- Raise `ElementError` / `ExternalError` from `core.errors`
- License detection: read first non-blank line of `LICENSE`, `LICENSE.md`,
  or `LICENSE.txt` at fetched dir root; truncate to 60 chars; else `None`

## Acceptance tests (in `test_vendor_github.py`)

All using the `GITHUB` vendor object directly (not the CLI):

1. `fetch` with a `/tree/<branch>/<subpath>` URL produces one
   `FetchedItem` with correct kind, name, origin, source_dir exists
2. `fetch` with root URL (`https://github.com/org/repo`) and no subpath
   produces a single item with `origin="github:org/repo"`
3. `fetch` with SSH URL works
4. `fetch` with invalid (non-GitHub) URL raises `ElementError`
5. `fetch` with `select=("something",)` raises `ElementError`
6. `list_source` returns expected names for a subpath (mock
   `git_sparse_checkout` to lay out files under workdir)
7. `deps` tuple includes a `git` entry; `deps[0].is_installed()` returns
   True in CI (git is always there); add a test that monkeypatches
   `shutil.which` to None and asserts `is_installed()` is False

Mock `git_ops.git_sparse_checkout` and `git_ops.git_clone` — no real
network.

## Definition of Done

1. `poetry run pytest tests/e2e/test_vendor_github.py -q` — all pass
2. Full suite: `poetry run pytest -q` — still green (old test_vendor.py
   still passes because commands/vendor.py unchanged)
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean

Do NOT commit.
