# Vendor Q0: shared git-repo cache + `refresh` CLI command

Build the shared cache layer that `buildwithclaude` and `tonsofskills`
will share. Also extend the CLI command-builder so any vendor exposing
a `refresh()` method gets a `vendor <v> refresh` subcommand.

## Goal

- `src/ai_dotfiles/vendors/_repo_cache.py` — clone-or-pull a git repo
  into `$AI_DOTFILES_HOME/.vendor-cache/<vendor>/`, honour a
  configurable TTL (default 24h), refresh on demand.
- `commands/vendor.py::_make_refresh_command` — new factory that
  attaches `vendor <v> refresh` when the vendor implements `refresh()`.

## File scope (exclusive)

- `src/ai_dotfiles/vendors/_repo_cache.py` (new)
- `tests/unit/test_repo_cache.py` (new)
- `src/ai_dotfiles/commands/vendor.py` — add the `refresh` factory and
  call-site in `_register_vendors`
- `tests/e2e/test_cli.py` — if a `VENDOR_*_SUBCOMMANDS` list changes,
  keep in sync (otherwise no change)

## Do NOT touch

- Other vendor modules (they'll use the cache in Q1/Q2)
- `base.py`, `source_file.py`, `placement.py`, `deps.py`
- README / blueprint (Q3 covers docs)

## Module design

```python
# _repo_cache.py

CACHE_SUBDIR = ".vendor-cache"
_SENTINEL = ".fetched-at"
DEFAULT_TTL_SECONDS = 60 * 60 * 24  # 24h


def cache_dir(vendor_name: str) -> Path:
    """Return $AI_DOTFILES_HOME/.vendor-cache/<vendor>/ — no mkdir."""

def is_fresh(cache_root: Path, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    """True iff <cache_root>/.fetched-at exists and mtime < ttl."""

def refresh(
    *,
    vendor_name: str,
    repo_url: str,
    branch: str = "main",
    force: bool = False,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Path:
    """Clone the repo into cache_dir(vendor_name), or git-fetch+reset
    if it already exists. Writes .fetched-at sentinel. Skips work when
    is_fresh is True unless force=True. Returns the cache path.

    Raises ExternalError on any git failure; ExternalError also if git
    is not on PATH.
    """

def find_skill_dirs(cache_root: Path) -> Iterator[Path]:
    """Yield every directory that directly contains a SKILL.md file,
    recursively. Sorted by path. Skips hidden dirs (.git, etc.)."""

def read_frontmatter(skill_md: Path) -> dict[str, str]:
    """Parse the YAML frontmatter at the top of SKILL.md into a dict.
    Missing or malformed frontmatter -> empty dict. Only scalar string
    values — lists (like `tags: [a, b]`) serialised as comma-joined
    string. No PyYAML — lightweight line parser."""
```

### Implementation notes

- `cache_dir` uses `ai_dotfiles.core.paths.storage_root()`.
- Use `subprocess.run(["git", ...], check=False, capture_output=True,
  text=True)` everywhere — wrap `FileNotFoundError` ("git missing") as
  `ExternalError("git executable not found; install from https://git-scm.com/")`.
- First-time clone:
  `git clone --depth=1 --branch <branch> <url> <cache>`
  (Skip sparse-checkout for simplicity; these repos are small enough
  to full-clone shallow. Note this deviation in code comment.)
- Refresh:
  `git -C <cache> fetch --depth=1 origin <branch>` then
  `git -C <cache> reset --hard origin/<branch>`
- Sentinel: write empty file `<cache>/.fetched-at` after successful
  clone/refresh. Use `path.touch()`.
- TTL check via `time.time() - sentinel.stat().st_mtime < ttl_seconds`.
- `mkdir(parents=True, exist_ok=True)` the parent of cache root.

### Frontmatter parser

Minimal YAML-like parser. SKILL.md usually starts with:
```
---
name: foo
description: Does foo stuff.
tags: [backend, api]
---
```

Accept `key: value` (strip quotes), `key: [a, b, c]` → `"a, b, c"`.
Stop at the second `---`. Tolerant of missing frontmatter (returns
`{}`). No external dep.

## `_make_refresh_command` (in `commands/vendor.py`)

Mirror `_make_search_command` pattern:

```python
def _make_refresh_command(vendor: Vendor) -> click.Command | None:
    refresh_method = getattr(vendor, "refresh", None)
    if refresh_method is None:
        return None

    @click.command(
        name="refresh",
        help=f"Re-fetch the '{vendor.name}' catalog cache.",
    )
    @click.option("-f", "--force", is_flag=True,
                  help="Re-fetch even if cache is still fresh.")
    def _refresh(force: bool) -> None:
        try:
            deps_mod.ensure(vendor)
            path = refresh_method(force=force)
        except AiDotfilesError as exc:
            ui.error(str(exc))
            sys.exit(exc.exit_code)
        ui.success(f"Cache refreshed: {path}")

    return _refresh
```

Attach in `_register_vendors` after the existing `find`/`search`
factory call:
```python
refresh_cmd = _make_refresh_command(v)
if refresh_cmd is not None:
    vendor_group.add_command(refresh_cmd)
```

## Hard rules

- mypy --strict clean; `X | None`; no print; absolute imports
- All subprocess calls via the module's own `_run` helper (defensive —
  future-proof for env isolation / cwd control). Raise `ExternalError`
  with stderr on non-zero exit.
- Tests mock `subprocess.run` — no real git.
- Tests use `tmp_path` + `monkeypatch.setenv("AI_DOTFILES_HOME", ...)` —
  never touch real `~/.ai-dotfiles`.
- Frontmatter parser: no external YAML dep.

## Acceptance tests (`test_repo_cache.py`)

≥10 cases. Mock `subprocess.run` where needed.

1. `cache_dir("foo")` resolves relative to `AI_DOTFILES_HOME`
2. `is_fresh` → False when sentinel missing
3. `is_fresh` → True when sentinel mtime within TTL
4. `is_fresh` → False when sentinel mtime past TTL
5. `refresh` first-time clones (captures `git clone --depth=1 ...`
   argv and writes sentinel)
6. `refresh` second-time no-op when fresh (no subprocess call)
7. `refresh(force=True)` always runs `git fetch + reset --hard`
8. `refresh` on stale cache runs `git fetch + reset --hard`
9. `refresh` raises `ExternalError` when `git clone` exits non-zero
10. `refresh` raises `ExternalError` when git binary missing
    (FileNotFoundError wrapping)
11. `find_skill_dirs` walks a tmp tree and yields only dirs with
    `SKILL.md`
12. `find_skill_dirs` skips hidden directories (`.git`, `.cache`)
13. `read_frontmatter` extracts `name`/`description`/`tags` from a
    sample file
14. `read_frontmatter` returns `{}` when no frontmatter
15. `read_frontmatter` is tolerant of malformed YAML-ish lines

## Definition of Done

1. `poetry run pytest tests/unit/test_repo_cache.py -q` — all pass
2. `poetry run pytest -q` — full suite (was 375) green
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean

Do NOT commit. Report files, gate outputs, deviations.
