"""Ownership state for MCP servers declared by domains.

When a domain's ``mcp.fragment.json`` contributes a server to
``<project>/.mcp.json``, the mapping ``server_name -> [domain, ...]`` is
recorded here so that ``remove`` / ``install`` can distinguish
domain-owned servers (safe to rewrite / drop) from user-authored ones
(never touched).

File location: ``<claude_dir>/.ai-dotfiles-mcp-ownership.json``.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

from ai_dotfiles.core.errors import ConfigError

OWNERSHIP_FILENAME = ".ai-dotfiles-mcp-ownership.json"


def ownership_path(claude_dir: Path) -> Path:
    """Return the ownership-file path for a given ``.claude`` directory."""
    return claude_dir / OWNERSHIP_FILENAME


def load_ownership(claude_dir: Path) -> dict[str, list[str]]:
    """Load the ownership map. Returns ``{}`` if the file does not exist.

    Raises :class:`ConfigError` on invalid JSON, wrong top-level shape,
    or malformed values.
    """
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
    result: dict[str, list[str]] = {}
    for key, value in data.items():
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(
                f"{path}: ownership value for {key!r} must be a list of strings"
            )
        result[str(key)] = list(value)
    return result


def save_ownership(claude_dir: Path, data: dict[str, list[str]]) -> None:
    """Write the ownership map atomically with sorted keys."""
    path = ownership_path(claude_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(dict(sorted(data.items())), indent=2) + "\n"
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(payload)
    os.replace(tmp, path)


def delete_ownership(claude_dir: Path) -> None:
    """Remove the ownership file if present; silent if already gone."""
    path = ownership_path(claude_dir)
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
