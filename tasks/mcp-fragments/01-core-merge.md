# Subtask 01: `core/mcp_merge.py` + unit tests

Self-contained module. Pure logic, no CLI deps. Must land before 02.

## Goal

Implement the `.mcp.json` merge pipeline mirroring the existing
`core/settings_merge.py`. Loads domain `mcp.fragment.json` files,
strips meta keys, merges into the on-disk `.mcp.json` while preserving
user-owned entries, computes permissions, and emits warnings for unset
`${VAR}` tokens and missing `_requires.npm` packages.

## File scope (exclusive)

- `src/ai_dotfiles/core/mcp_merge.py`        (new)
- `tests/unit/test_mcp_merge.py`             (new)

## Do NOT touch

- Any command module (`commands/*.py`) — subtask 03's job.
- `core/elements.py`, `core/symlinks.py` — subtask 03.
- `core/mcp_ownership.py` — subtask 02.
- `ui.py` — no imports from `ui` here; callers pass a `warn` callable.

## Hard rules

- mypy `--strict` clean; `X | None`; absolute imports from `ai_dotfiles.core.*`.
- Raise `ConfigError` (from `ai_dotfiles.core.errors`) on malformed
  fragments / JSON.
- No `print`; warnings flow through an injected `Callable[[str], None]`.
- Deterministic ordering: iterate fragments in caller-supplied order,
  **not** path-sorted (the caller determines order via manifest
  insertion order — matches how domain ordering is used elsewhere in
  the codebase).
- Per-server values stored/written as opaque `dict[str, Any]` — any
  server-level key (`command`, `args`, `env`, `type`, `url`, `headers`,
  `oauth`, `headersHelper`, …) round-trips verbatim.
- `_ENV_TOKEN_RE` must match `${VAR}` and `${VAR:-default}` (bash-style);
  it must NOT match `${env:VAR}` (the user's original spec mentioned
  this syntax but Claude Code does not support it).

## Implementation sketch

```python
# src/ai_dotfiles/core/mcp_merge.py
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from ai_dotfiles.core.elements import ElementType, parse_element
from ai_dotfiles.core.errors import ConfigError

_META_KEYS: tuple[str, ...] = ("_domain", "_description", "_requires")

# Claude Code env-var syntax: ${VAR} or ${VAR:-default}. NOT ${env:VAR}.
_ENV_TOKEN_RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}"
)


def load_mcp_fragment(path: Path) -> dict[str, Any]:
    """Read mcp.fragment.json (or .mcp.json-shaped file). {} if missing."""


def strip_mcp_meta(fragment: dict[str, Any]) -> dict[str, Any]:
    """Remove _domain, _description, _requires."""


def collect_mcp_fragments(
    packages: list[str], catalog: Path
) -> list[tuple[str, Path]]:
    """Iterate packages in list order; for each @domain specifier, yield
    (domain_name, catalog/<domain>/mcp.fragment.json) when file exists."""


def assemble_mcp_servers(
    fragments: list[tuple[str, Path]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Merge fragments. Returns (servers, ownership).
    - servers: server_name -> last-seen per-server dict
    - ownership: server_name -> [domain, ...] in encounter order
      (all contributing domains tracked, even when overridden)"""


def derive_mcp_permissions(server_names: Iterable[str]) -> list[str]:
    """[`mcp__<name>__*` for each name] — deterministic order, dedup."""


def detect_collisions(
    new_servers: dict[str, dict[str, Any]],
    existing: dict[str, Any],
    previous_ownership: dict[str, list[str]],
) -> list[str]:
    """Names present in both existing.mcpServers AND new_servers,
    but NOT in previous_ownership → first-time collisions (user wins)."""


def merge_with_existing_mcp(
    new_servers: dict[str, dict[str, Any]],
    existing: dict[str, Any],
    previous_ownership: dict[str, list[str]],
) -> dict[str, Any]:
    """Compose final .mcp.json payload per rules in plan:
       - Preserve user-owned servers (not in previous_ownership).
       - Drop previously-owned-but-now-missing servers.
       - Apply new_servers, but skip any first-time collisions.
       - Preserve non-`mcpServers` top-level keys from existing."""


def write_mcp_json(data: dict[str, Any], target: Path) -> None:
    """indent=2 + trailing newline; mkdir parents."""


def backup_mcp_json(
    target: Path, backup_root: Path, project_name: str
) -> Path | None:
    """Copy target to backup_root/.claude-mcp/<project_name>/.mcp.json.<ts>
    where ts = UTC ISO8601 with ':' replaced by '-' for cross-platform
    safety. No-op if target absent. Never overwrites: if same-second
    collision, append a counter."""


def warn_unset_env_vars(
    servers: dict[str, dict[str, Any]],
    warn: Callable[[str], None],
) -> None:
    """Walk string values recursively; find _ENV_TOKEN_RE matches; warn
    once per name whose default is None AND os.environ doesn't have it."""


def warn_missing_npm_requires(
    fragments: list[tuple[str, Path]],
    project_root: Path,
    warn: Callable[[str], None],
) -> None:
    """Read project_root/package.json; union deps+devDeps. For each
    fragment's `_requires.npm`, warn per missing package with suggested
    install command. Silent if package.json missing or unreadable."""
```

### Collision policy (copy exactly)

```
first-time collision (name not in previous_ownership):
    user server stays; domain server NOT written; caller warns.
repeat collision (name in previous_ownership):
    domain server overwrites; no warning.
```

### Backup path format (copy exactly)

```
<backup_root>/.claude-mcp/<project_name>/.mcp.json.<UTC-ISO-no-colons>[.N]
```

Timestamp example: `2026-04-22T14-33-07Z`; suffix `.1`, `.2` appended
if same-second collision.

## Acceptance tests (`tests/unit/test_mcp_merge.py`)

Required test names — see plan for full list. Highlights:

- `test_load_mcp_fragment_existing`
- `test_load_mcp_fragment_missing_returns_empty`
- `test_load_mcp_fragment_invalid_json_raises_config_error`
- `test_strip_mcp_meta_removes_underscored_keys`
- `test_collect_mcp_fragments_only_domain_specifiers`
- `test_collect_mcp_fragments_missing_file_skipped`
- `test_assemble_mcp_servers_single_domain`
- `test_assemble_mcp_servers_multi_domain_no_overlap`
- `test_assemble_mcp_servers_conflict_last_wins_ownership_records_both`
- `test_assemble_mcp_servers_preserves_http_type_url_headers`
- `test_derive_mcp_permissions_produces_wildcards`
- `test_merge_preserves_user_servers`
- `test_merge_drops_stale_domain_servers`
- `test_merge_updates_changed_domain_servers_when_in_prev_ownership`
- `test_merge_first_time_collision_user_wins`
- `test_merge_repeat_collision_domain_wins`
- `test_detect_collisions_returns_first_time_collisions_only`
- `test_write_mcp_json_indent_and_newline`
- `test_backup_mcp_json_no_source_returns_none`
- `test_backup_mcp_json_timestamps_unique`   (hint: monkeypatch `datetime.utcnow` or use an injectable clock)
- `test_warn_unset_env_vars_finds_pattern_once_per_var`
- `test_warn_unset_env_vars_skips_tokens_with_default`
- `test_warn_missing_npm_requires_no_package_json_silent`
- `test_warn_missing_npm_requires_flags_missing_dep`
- `test_warn_missing_npm_requires_present_silent`

Use `tmp_path` and `monkeypatch` only — no fixtures that touch real
`~/.ai-dotfiles/` or `~/.claude/`. Warnings collected into a
`list[str]` via a lambda passed as the `warn` callable.

## Definition of Done

1. `poetry run pytest tests/unit/test_mcp_merge.py -q` — green
2. `poetry run pytest -q` — full suite green (nothing else should break)
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean (`--fix` if needed)
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean

Do NOT commit. Orchestrator commits after all subtasks land.
