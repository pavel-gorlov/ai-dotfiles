# Subtask 02: `core/mcp_ownership.py` + unit tests

Tiny module — state file CRUD. Depends on nothing except `core/errors`.
Must land after 01 (no import dependency between them, but merge wins
are read in 03, so we land them in order).

## Goal

Persist and load the domain-ownership map for MCP servers:
`{server_name: [domain1, domain2, ...]}`. Atomic writes, sorted keys,
silent no-ops on missing files.

## File scope (exclusive)

- `src/ai_dotfiles/core/mcp_ownership.py`   (new)
- `tests/unit/test_mcp_ownership.py`         (new)

## Do NOT touch

- `core/mcp_merge.py` — subtask 01.
- Any command module — subtask 03.
- Anything else.

## Hard rules

- mypy `--strict`; absolute imports; no `print`.
- File path: `<claude_dir>/.ai-dotfiles-mcp-ownership.json`. Name
  exported as module constant `OWNERSHIP_FILENAME`.
- Atomic write: write to `<target>.tmp` then `os.replace(tmp, target)`
  — no partial file on crash.
- Sorted keys in output (determinism for diffs).
- `indent=2` + trailing newline (match other JSON files in this repo).
- Raise `ConfigError` on malformed JSON; `{}` on missing file.

## Implementation sketch

```python
# src/ai_dotfiles/core/mcp_ownership.py
from __future__ import annotations

import json
import os
from pathlib import Path

from ai_dotfiles.core.errors import ConfigError

OWNERSHIP_FILENAME = ".ai-dotfiles-mcp-ownership.json"


def ownership_path(claude_dir: Path) -> Path:
    return claude_dir / OWNERSHIP_FILENAME


def load_ownership(claude_dir: Path) -> dict[str, list[str]]:
    path = ownership_path(claude_dir)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object at top level")
    # Validate shape minimally: every value is list[str].
    result: dict[str, list[str]] = {}
    for key, value in data.items():
        if not isinstance(value, list) or not all(
            isinstance(v, str) for v in value
        ):
            raise ConfigError(
                f"{path}: ownership value for {key!r} must be a list of strings"
            )
        result[str(key)] = list(value)
    return result


def save_ownership(claude_dir: Path, data: dict[str, list[str]]) -> None:
    path = ownership_path(claude_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(dict(sorted(data.items())), indent=2) + "\n"
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(payload)
    os.replace(tmp, path)


def delete_ownership(claude_dir: Path) -> None:
    path = ownership_path(claude_dir)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
```

## Acceptance tests (`tests/unit/test_mcp_ownership.py`)

- `test_load_missing_returns_empty` — fresh `tmp_path`; no file → `{}`.
- `test_save_then_load_roundtrip_sorted_keys` — insert out-of-order
  keys, save, reload, assert file contents are sorted (read raw JSON
  text and confirm key order).
- `test_delete_idempotent` — call twice in a row, neither raises.
- `test_save_atomic_does_not_leave_tmp_on_success` — after a clean
  save, the `.tmp` sidecar does not exist.
- `test_load_invalid_json_raises_config_error`
- `test_load_wrong_shape_raises_config_error` — e.g.
  `{"server": "not-a-list"}`.

No monkeypatching required; pure filesystem.

## Definition of Done

1. `poetry run pytest tests/unit/test_mcp_ownership.py -q` — green
2. `poetry run pytest -q` — full suite green
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean

Do NOT commit.
