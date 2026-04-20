# Vendor P2: add `paks` vendor

Add `stakpak/paks` as a third vendor sibling to `skills_sh` and
`github`. Reuse the shared `.source`, placement, deps, and CLI group
builder — no changes to the framework itself.

Prereq: P0 (Dependency schema) and P1 (`find` → `search` rename) have
already landed.

## Goal

Expose:
```
ai-dotfiles vendor paks install <source> [--force]
ai-dotfiles vendor paks list <source>
ai-dotfiles vendor paks search <query>
ai-dotfiles vendor paks deps check
```

Treat one `source` as one skill. No `--select`. Route output via
`paks install --dir <workdir>` (HOME override only as fallback).

## File scope

**Create**:

- `src/ai_dotfiles/vendors/paks.py` — frozen dataclass
  `_PaksVendor` + module-level singleton `PAKS`
- `tests/e2e/test_vendor_paks.py` — mocked subprocess coverage for
  `list_source`, `fetch`, `search`, `deps`

**Edit**:

- `src/ai_dotfiles/vendors/__init__.py` — add
  `"paks": cast(Vendor, PAKS)` to `REGISTRY`; update `__all__` export
- `README.md` — add `vendor paks ...` entries to the Vendoring table
  and an "Example: paks" block similar to the skills.sh one
- `ai-dotfiles-blueprint.md` — add paks to the Vendor plugins section

**Do NOT touch**: any other vendor module, CLI layer, test. Don't
modify `commands/vendor.py` — the registry loop picks paks up
automatically (plus any duck-typed `search`).

## `_PaksVendor` implementation

### Dependency
```python
_PAKS_DEPENDENCY = Dependency(
    name="paks",
    check=lambda: shutil.which("paks") is not None,
    install_url="https://paks.stakpak.dev",
)
```

### Attributes
```python
name: str = "paks"
display_name: str = "paks"
description: str = "Install Claude Code skills from the paks registry."
deps: tuple[Dependency, ...] = (_PAKS_DEPENDENCY,)
```

### `list_source(source) -> Iterable[str]`
Return `[source]`. Single-skill semantics; no subprocess call.

### `fetch(source, *, select, workdir) -> list[FetchedItem]`
```python
if select:
    raise ElementError(
        "paks vendor does not support --select; install one source at a time"
    )

workdir.mkdir(parents=True, exist_ok=True)
out = workdir / "out"
out.mkdir(parents=True, exist_ok=True)

argv = ["paks", "install", source,
        "--agent", "claude-code",
        "--scope", "global",
        "--dir", str(out),
        "--yes"]
result = _run(argv, cwd=workdir, env={"PATH": os.environ["PATH"]})
if result.returncode != 0:
    raise ExternalError(f"paks install failed: {result.stderr.strip()}")
```

Enumerate `out/.claude/skills/*/` (directories only). If empty, try
`out/*/` as a fallback (paks layout may vary with flags). Each
materialized dir becomes a `FetchedItem(kind="skill", name=dir.name,
source_dir=dir, origin=f"paks:{source}", license=_detect_license(dir))`.
Reuse the same `_detect_license` helper pattern as `skills_sh` (copy
the function verbatim — 6 lines; splitting into a shared helper is a
follow-up refactor).

If no skills materialize, raise
`ExternalError("paks install produced no skills at <out>.")`.

### `search(query) -> list[SearchResult]`
```python
argv = ["paks", "search", query, "--format", "json"]
```

Expect a JSON array of objects. Fields we care about per result
(guess based on upstream convention; verify during smoke):
`source` / `name` / `description` / `url`. Be lenient — default
missing fields to `""`.

If JSON parsing fails (upstream prints a table instead), fall back to
a simple tabular parser similar to `_parse_search_output` in
`skills_sh.py` — add a minimal version here.

Reuse the same `SearchResult` dataclass if it's module-importable
from `skills_sh`; otherwise define a local `SearchResult` with the
same fields. (Simpler: define local; can dedupe later.)

Raise `ExternalError` on non-zero exit or empty result.

### `_subprocess_env` / `_run`
Copy the minimal patterns from `skills_sh`, stripping the HOME
override (paks doesn't need it). Only forward `PATH`.

## Tests

**`tests/e2e/test_vendor_paks.py` covers** (≥12 cases, all mocked):

1. `list_source(source)` returns `[source]` with no subprocess call
2. `deps` tuple contains `paks` entry; `is_installed()` True with
   `shutil.which` monkeypatched
3. `deps.is_installed()` False when paks missing
4. `fetch` happy path: two skill dirs materialized under `out/.claude/skills/`
5. `fetch` fallback layout: skills directly under `out/`
6. `fetch` with `select=("x",)` → `ElementError`
7. `fetch` non-zero exit → `ExternalError` with stderr
8. `fetch` empty result → `ExternalError`
9. `fetch` argv contains `--agent claude-code --scope global --dir <...> --yes`
10. `search(query)` with JSON output parses correctly
11. `search(query)` with non-zero exit → `ExternalError`
12. `search(query)` empty results → `ExternalError`
13. License detection on one of the fetch happy-path skills
14. Vendor metadata (`name`, `display_name`, `description`,
    `isinstance(PAKS, Vendor)`)

Mock `subprocess.run` in `ai_dotfiles.vendors.paks.subprocess.run`;
fake the on-disk layout via `side_effect`.

## Docs

**README.md** — after the Example: skills.sh block add:

```markdown
#### Example: paks

```bash
# One-time: install paks (https://paks.stakpak.dev)
brew tap stakpak/stakpak && brew install paks

# Check it's wired up
ai-dotfiles vendor paks deps check

# Search the paks registry
ai-dotfiles vendor paks search kubernetes

# Install one skill
ai-dotfiles vendor paks install kubernetes-deploy
ai-dotfiles add skill:kubernetes-deploy
```
```

Also add a row to the Vendoring command table.

**ai-dotfiles-blueprint.md** — one-paragraph mention in the Vendor
plugins section, noting paks is a native Rust CLI (opt-in dep).

## Hard rules

- mypy `--strict` clean; `X | None`; no print; absolute imports
- Module `paks.py` stays self-contained (no imports from `skills_sh`)
- Tests mock `subprocess.run` — no real `paks` invocation

## Definition of Done

1. `poetry run pytest tests/e2e/test_vendor_paks.py -q` — all pass
2. `poetry run pytest -q` — full suite green
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean
7. `poetry run ai-dotfiles vendor --help` lists `paks` among vendors
8. `poetry run ai-dotfiles vendor paks --help` lists `install`,
   `list`, `search`, `deps`
9. `poetry run ai-dotfiles vendor paks deps check` — exits 1 with a
   URL line if paks not installed; 0 otherwise

Do NOT commit. Report files, gate outputs, deviations, any empirical
findings that should inform a follow-up smoke run.
