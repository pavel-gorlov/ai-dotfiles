# Step 2c: core/manifest.py

## Goal

CRUD operations for manifest files (`ai-dotfiles.json` and `global.json`). Both have identical format: `{"packages": [...]}`.

## File: `src/ai_dotfiles/core/manifest.py`

### Functions

```python
import json
from pathlib import Path

def read_manifest(path: Path) -> dict:
    """Read and return manifest JSON. 
    If file doesn't exist, return {"packages": []}.
    If file exists but is invalid JSON, raise click.FileError."""

def write_manifest(path: Path, data: dict) -> None:
    """Write manifest as JSON with indent=2 and trailing newline.
    Create parent directories if needed."""

def get_packages(path: Path) -> list[str]:
    """Shortcut: read manifest and return packages list."""

def add_packages(path: Path, items: list[str]) -> list[str]:
    """Append items to packages list (skip duplicates).
    Write back. Return list of actually-added items (new ones only)."""

def remove_packages(path: Path, items: list[str]) -> list[str]:
    """Remove items from packages list.
    Write back. Return list of actually-removed items."""

def set_metadata(path: Path, key: str, value: str) -> None:
    """Set a top-level key in manifest (e.g. "stack": "backend").
    Used by stack apply."""
```

### Manifest format

```json
{
  "packages": [
    "@python",
    "skill:code-review",
    "agent:researcher",
    "rule:security"
  ],
  "stack": "backend"
}
```

- `packages` is always a list of strings
- `stack` is optional, set by `stack apply`
- Order in `packages` is preserved (insertion order)
- Duplicates are prevented on add

## File: `tests/test_manifest.py`

### Test cases

1. `test_read_missing_file` — returns `{"packages": []}`
2. `test_read_existing_file` — returns parsed content
3. `test_read_invalid_json` — raises error
4. `test_write_creates_file` — file created with correct content
5. `test_write_creates_parent_dirs` — intermediate dirs created
6. `test_write_indent_and_newline` — output has indent=2 and trailing `\n`
7. `test_get_packages_empty` — returns `[]` for missing file
8. `test_get_packages_populated` — returns list from file
9. `test_add_packages_new` — adds items, returns them
10. `test_add_packages_duplicate` — existing items skipped, not returned
11. `test_add_packages_mixed` — some new, some existing
12. `test_add_packages_to_missing_file` — creates file with items
13. `test_remove_packages_existing` — removes items, returns them
14. `test_remove_packages_missing` — items not in list, returns empty
15. `test_remove_packages_mixed` — some found, some not
16. `test_set_metadata` — adds key to manifest

## Dependencies

- `json` (stdlib)
- `click` (for error types)

## Definition of Done

- [ ] `src/ai_dotfiles/core/manifest.py` exists with all functions
- [ ] `tests/unit/test_manifest.py` exists with all 16 test cases
- [ ] `poetry run pytest tests/unit/test_manifest.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/core/manifest.py` — passes strict mode
- [ ] All public functions have type annotations (params + return)
- [ ] Errors raise `ConfigError` (from `core.errors`), not raw exceptions
- [ ] JSON output is deterministic (indent=2, trailing newline)
- [ ] add_packages is idempotent (no duplicates)

## Commit

Part of batch commit after all Step 2 sub-tasks complete.
