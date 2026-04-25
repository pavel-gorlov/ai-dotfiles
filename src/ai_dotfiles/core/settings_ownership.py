"""Ownership state for settings.json entries written by ai-dotfiles.

Mirrors :mod:`mcp_ownership` for ``settings.json``. When the CLI
regenerates ``<claude_dir>/settings.json`` from domain fragments (plus
MCP-derived entries), it records here exactly what it added:

* the strings it injected into ``permissions.allow`` / ``deny`` / ``ask``
* a stable signature for every hook entry it inserted into ``hooks``

On the next rebuild we strip those entries from the existing
``settings.json`` before merging the new fragments — so user-authored
keys survive, but stale domain leftovers are cleaned up. Without this
file we cannot tell apart "the user wrote this" from "we wrote this
last time", and the file would grow forever.

Location: ``<claude_dir>/.ai-dotfiles-settings-ownership.json``.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

from ai_dotfiles.core.errors import ConfigError

OWNERSHIP_FILENAME = ".ai-dotfiles-settings-ownership.json"

_DEFAULT: dict[str, list[str]] = {
    "permissions_allow": [],
    "permissions_deny": [],
    "permissions_ask": [],
    "hooks_signatures": [],
}


def ownership_path(claude_dir: Path) -> Path:
    """Return the settings-ownership file path for a ``.claude`` dir."""
    return claude_dir / OWNERSHIP_FILENAME


def load_settings_ownership(claude_dir: Path) -> dict[str, list[str]]:
    """Load the ownership map. Missing keys default to empty lists.

    Returns the four-key default dict if the file is absent. Raises
    :class:`ConfigError` on invalid JSON or wrong shape.
    """
    path = ownership_path(claude_dir)
    if not path.exists():
        return {k: list(v) for k, v in _DEFAULT.items()}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object at top level")
    result: dict[str, list[str]] = {k: list(v) for k, v in _DEFAULT.items()}
    for key in _DEFAULT:
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"{path}: '{key}' must be a list of strings")
        result[key] = list(value)
    return result


def save_settings_ownership(claude_dir: Path, data: dict[str, list[str]]) -> None:
    """Atomic write with deterministic key/value ordering."""
    path = ownership_path(claude_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    for key in _DEFAULT:
        value = data.get(key, [])
        payload[key] = (
            sorted(set(value))
            if all(isinstance(v, str) for v in value)
            else list(value)
        )
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def delete_settings_ownership(claude_dir: Path) -> None:
    """Remove the ownership file if present; silent if already gone."""
    path = ownership_path(claude_dir)
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def is_empty(data: dict[str, list[str]]) -> bool:
    """Return True if every tracked list is empty."""
    return all(not data.get(k) for k in _DEFAULT)
