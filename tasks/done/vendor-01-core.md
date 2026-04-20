# Vendor V1: core framework

Build the shared vendor subsystem: abstract protocol, `.source` metadata
I/O, placement into catalog, and dependency plumbing. No vendor
implementations yet — that's V2/V3.

## Goal

Create the `src/ai_dotfiles/vendors/` package with everything a vendor
plugin needs but no plugins themselves. Everything tested at unit level
with `tmp_path`.

## File scope (exclusive — write only these)

- `src/ai_dotfiles/vendors/__init__.py` — `REGISTRY: dict[str, Vendor]` (empty for now)
- `src/ai_dotfiles/vendors/base.py` — `Vendor` Protocol, `Dependency`, `FetchedItem`, `SourceMeta` types
- `src/ai_dotfiles/vendors/source_file.py` — `read(path) -> SourceMeta | None`, `write(path, *, vendor, origin, tool, license) -> None`
- `src/ai_dotfiles/vendors/placement.py` — `place_item(item, *, catalog_root, force, vendor_name) -> Path`
- `src/ai_dotfiles/vendors/deps.py` — `ensure(vendor) -> None`, `check(vendor) -> list[Dependency]` (missing), `install(vendor, *, yes=False) -> None`
- `tests/unit/test_source_file.py`
- `tests/unit/test_placement.py`
- `tests/unit/test_deps.py`

## Do NOT touch

- `src/ai_dotfiles/commands/vendor.py` (rewritten in V4)
- `src/ai_dotfiles/core/**` (unchanged)
- `cli.py`
- Any other command file

## Hard rules

- Full type annotations; `mypy --strict` clean
- `X | None` syntax (PEP 604)
- No `print()` — use `ui.*` for any command-side output; in core modules
  return data / raise errors, don't print
- Raise `ai_dotfiles.core.errors.ExternalError` for missing deps and
  subprocess failures; `ElementError` for destination-exists / invalid
  name / etc.
- Absolute imports: `from ai_dotfiles.core.errors import ExternalError`
- Python 3.12 features OK (structural pattern matching, `Self`, etc.)
- `frozen=True` dataclasses where appropriate
- Keep modules focused: no vendor plugin code here

## Details

### `base.py`

```python
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class Dependency:
    name: str
    check: Callable[[], bool]
    install_cmd: dict[str, list[str]]  # keyed by sys.platform prefix: "darwin", "linux", "win32"
    manual_hint: str

    def is_installed(self) -> bool:
        return self.check()


@dataclass(frozen=True)
class FetchedItem:
    kind: Literal["skill", "agent", "rule"]
    name: str
    source_dir: Path
    origin: str
    license: str | None


@dataclass(frozen=True)
class SourceMeta:
    vendor: str
    origin: str
    tool: str
    fetched: str  # ISO date YYYY-MM-DD
    license: str  # "unknown" if not detected


@runtime_checkable
class Vendor(Protocol):
    name: str
    display_name: str
    description: str
    deps: tuple[Dependency, ...]

    def list_source(self, source: str) -> Iterable[str]: ...
    def fetch(
        self,
        source: str,
        *,
        select: tuple[str, ...] | None,
        workdir: Path,
    ) -> list[FetchedItem]: ...
```

### `__init__.py`

```python
from ai_dotfiles.vendors.base import Vendor

REGISTRY: dict[str, Vendor] = {}
```

Vendors register themselves in V2/V3 by populating this dict at import
time in `commands/vendor.py` (not here, to avoid circular imports).

### `source_file.py`

- Format: plain text, one key-value per line, `key: value`.
- Keys written in order: `vendor`, `origin`, `tool`, `fetched`, `license`.
- `write(target: Path, *, vendor: str, origin: str, tool: str, license: str | None) -> None`:
  - `target` is the directory of a vendored item (e.g. `catalog/skills/foo/`)
  - Writes `target / ".source"` with the five lines
  - `fetched` is today's UTC date
  - If `license is None` or empty, write `unknown`
- `read(target: Path) -> SourceMeta | None`:
  - Returns `None` if file missing
  - Parses line-by-line; tolerant of extra whitespace, strict on required keys
  - Raises `ConfigError` if file exists but malformed

### `placement.py`

```python
def place_item(
    item: FetchedItem,
    *,
    catalog_root: Path,
    force: bool,
    vendor_name: str,
) -> Path:
    """Move item.source_dir -> catalog_root/<kind>s/<name>/, write .source, return final path."""
```

- Destination: `catalog_root / f"{item.kind}s" / item.name`
- If destination exists and not `force` → `ElementError` with message
  `"Already exists: {path}. Use --force to overwrite."`
- If `force` and destination exists → `shutil.rmtree(destination)` then move
- Use `shutil.move(item.source_dir, destination)` (works across devices)
- After move, call `source_file.write(destination, vendor=vendor_name,
  origin=item.origin, tool="ai-dotfiles vendor", license=item.license)`

### `deps.py`

- `check(vendor: Vendor) -> list[Dependency]` — returns list of missing deps
- `ensure(vendor: Vendor) -> None`:
  - calls `check`; if non-empty, raises `ExternalError` with a clear
    message listing missing deps and the install command hint
    (`ai-dotfiles vendor <vendor.name> deps install`)
- `install(vendor: Vendor, *, yes: bool = False) -> None`:
  - for each missing dep:
    - resolve platform via `sys.platform`; pick `install_cmd[key]`
    - if not present for platform → raise `ExternalError` with
      `dep.manual_hint`
    - if `yes` is False → prompt via `click.confirm("Run: {cmd}?")`;
      abort on no
    - `subprocess.run(cmd, check=True)`
  - On macOS, if `install_cmd["darwin"]` starts with `brew` but `brew`
    itself is missing → raise with clear hint
  - Do not use `sudo` anywhere — if a command would need it, treat as
    manual-hint only

## Tests

### `test_source_file.py` (≥10 cases)

- write happy path → file exists with expected format
- license=None writes `unknown`
- fetched date is today
- read happy path → SourceMeta
- read missing file → None
- read malformed file → ConfigError
- round-trip write+read
- overwrite existing file
- empty vendor/origin rejected (ValueError)
- newline at EOF

### `test_placement.py` (≥8 cases)

- happy path moves dir and writes .source
- destination exists + not force → ElementError
- destination exists + force → overwrites
- .source file contents correct
- creates parent dirs
- kind="agent" uses `agents/` subdir
- kind="rule" uses `rules/` subdir
- source_dir missing → propagates FileNotFoundError

### `test_deps.py` (≥6 cases)

- check returns missing deps
- check returns [] when all present
- ensure raises ExternalError with install hint
- ensure succeeds silently when all present
- install runs subprocess.run with correct command (mock)
- install raises when platform unsupported and manual_hint referenced

Use `pytest` mocks (`monkeypatch.setattr` on `subprocess.run`,
`shutil.which`) — no real subprocess invocations in unit tests.

## Definition of Done

1. `poetry run pytest tests/unit/test_source_file.py tests/unit/test_placement.py tests/unit/test_deps.py -q` — all pass
2. `poetry run pytest -q` — full suite green (previous 261 still pass + new ones)
3. `poetry run mypy src/` — clean (strict)
4. `poetry run ruff check src/ tests/` — clean (run `--fix` if needed)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — all hooks pass

Do NOT commit. Orchestrator runs gates independently and commits.
