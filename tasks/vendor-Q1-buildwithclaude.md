# Vendor Q1: `buildwithclaude` vendor

Add a new vendor backed by https://github.com/davepoon/buildwithclaude
(500+ free Claude Code extensions, MIT-ish). Sparse-clone the repo via
the shared `_repo_cache` (Q0), index `SKILL.md` files, support
`search`/`install`/`list`/`refresh`/`deps check`.

## File scope

- `src/ai_dotfiles/vendors/buildwithclaude.py` (new)
- `tests/e2e/test_vendor_buildwithclaude.py` (new)
- `src/ai_dotfiles/vendors/__init__.py` — register `BUILDWITHCLAUDE`
  in REGISTRY and `__all__`

## Do NOT touch

- Other vendor modules
- `_repo_cache.py` (already built in Q0)
- `commands/vendor.py` (already extended in Q0)
- README / blueprint (Q3)

## Real-layout probe (first step of implementation)

Before writing production code, spend ~5 min on an empirical check:

```bash
TMP=$(mktemp -d)
git clone --depth=1 https://github.com/davepoon/buildwithclaude.git "$TMP/bwc"
find "$TMP/bwc" -name SKILL.md | head -20
cat "$TMP/bwc/.claude-plugin/marketplace.json" 2>/dev/null | head -30 || true
tree -L 3 "$TMP/bwc" 2>/dev/null | head -60 || ls -la "$TMP/bwc"
rm -rf "$TMP"
```

Document the observed layout in a module docstring. Expected: a tree
like `plugins/<pluginname>/skills/<skillname>/SKILL.md` OR
`skills/<skillname>/SKILL.md`. Use whatever actually exists — don't
assume.

## Module shape

```python
@dataclass(frozen=True)
class _BuildWithClaudeVendor:
    name: str = "buildwithclaude"
    display_name: str = "buildwithclaude"
    description: str = "Install skills from the buildwithclaude marketplace."
    deps: tuple[Dependency, ...] = (_GIT_DEPENDENCY,)  # local dep, not shared import

    def list_source(self, source: str) -> Iterable[str]: ...
    def search(self, query: str) -> list[SearchResult]: ...
    def fetch(self, source, *, select, workdir) -> list[FetchedItem]: ...
    def refresh(self, *, force: bool = False) -> Path: ...
```

`_REPO_URL = "https://github.com/davepoon/buildwithclaude.git"`.

### `list_source(source)`
Single-skill semantics. Return `[source]`. No subprocess.

### `refresh(force=False)`
Delegate to `_repo_cache.refresh(vendor_name="buildwithclaude",
repo_url=_REPO_URL, branch="main", force=force)`. Return the cache path.

### `search(query)`
1. Call `refresh(force=False)` (auto-refresh if stale).
2. Walk `_repo_cache.find_skill_dirs(cache_root)`.
3. For each skill: read frontmatter, take `name` (fallback to dir
   name), `description`, `tags`.
4. Substring match (case-insensitive) against name + description +
   tags. Return `SearchResult` list.
5. Empty query → raise `ValueError`.
6. Empty results → raise `ExternalError("no results for query=…")`.

`SearchResult` fields (define locally):
- `source` (the marketplace name, always `"buildwithclaude"`)
- `name` (skill name)
- `description`
- `url` (`https://github.com/davepoon/buildwithclaude/tree/main/<relpath>`)
- `installs` (empty string — no counts available)

### `fetch(source, *, select, workdir)`
1. `if select: raise ElementError("--select not supported")`.
2. `refresh(force=False)`.
3. `find_skill_dirs` and look for one matching `source` (by dir name).
   If 0 matches → `ExternalError`. If >1 → `ExternalError` asking user
   to be more specific (unlikely but defensive).
4. `shutil.copytree(match, workdir/out/<source>)`.
5. Produce one `FetchedItem(kind="skill", name=source,
   source_dir=workdir/out/<source>, origin=f"buildwithclaude:{source}",
   license=_detect_license(match))`.

`_detect_license`: reuse the same first-line-of-LICENSE helper pattern
(copy from `paks.py` / `skills_sh.py`).

### Registration (`vendors/__init__.py`)

```python
from ai_dotfiles.vendors.buildwithclaude import BUILDWITHCLAUDE
# ...
REGISTRY = {
    ...,
    "buildwithclaude": cast(Vendor, BUILDWITHCLAUDE),
}
__all__ += ["BUILDWITHCLAUDE"]
```

## Hard rules

- mypy --strict clean; `X | None`; no print; absolute imports
- Module self-contained — don't import from `paks`/`skills_sh`. Copy
  small helpers (license detection). Refactor to shared helper is a
  follow-up.
- Tests mock `_repo_cache.refresh` and pre-populate a fake cache dir
  on `tmp_path`. No real git calls.
- Use real fixtures (capture sample `SKILL.md` with frontmatter).
- CLI registration is picked up by the dynamic builder from Q0 —
  no additional CLI-layer code.

## Acceptance tests (≥10 cases)

1. `list_source("foo")` returns `["foo"]` without touching filesystem
2. `search` happy path: fake cache with 3 SKILL.md, query matches 2
3. `search` matches description text (not just name)
4. `search` matches tags
5. `search` empty query → ValueError
6. `search` no matches → ExternalError
7. `refresh(force=True)` delegates to `_repo_cache.refresh(force=True)`
8. `fetch` happy path copies one dir into `workdir/out/<name>`
9. `fetch` with `select=("x",)` → ElementError
10. `fetch` unknown source → ExternalError
11. `fetch` detects license file when present
12. Registration: `from ai_dotfiles.vendors import REGISTRY;
    assert "buildwithclaude" in REGISTRY`
13. `deps` tuple has `git`; `is_installed()` matches `shutil.which`
14. Vendor metadata (`name`/`display_name`/`description`,
    `isinstance(BUILDWITHCLAUDE, Vendor)`)

## DoD

1. `poetry run pytest tests/e2e/test_vendor_buildwithclaude.py -q` — all pass
2. `poetry run pytest -q` — full suite green
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean
7. Manual: `poetry run ai-dotfiles vendor buildwithclaude --help`
   lists `install`, `list`, `search`, `refresh`, `deps`

Do NOT commit. Report files, gate outputs, empirical layout findings
(important for Q3 docs), deviations.
