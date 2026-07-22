"""Ownership state for MCP servers written into ``.codex/config.toml``.

When a domain's ``mcp.fragment.json`` contributes a server to the
``[mcp_servers]`` table of ``<project>/.codex/config.toml``, the mapping
``server_name -> [domain, ...]`` is recorded here so that ``remove`` /
``install`` can distinguish domain-owned servers (safe to rewrite /
drop) from user-authored ones (never touched).

This is the Codex-side analogue of
:mod:`ai_dotfiles.core.mcp_ownership` (which tracks ``.mcp.json``
servers for the Claude target). The two targets keep separate ownership
files because their config surfaces are independent.

File location: ``.ai-dotfiles-mcp-ownership.json`` inside the Codex
config directory (``<project>/.codex`` or ``$CODEX_HOME``) — a sidecar
next to ``config.toml``.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

from ai_dotfiles.core.errors import ConfigError

OWNERSHIP_FILENAME = ".ai-dotfiles-mcp-ownership.json"


def mcp_ownership_path(codex_dir: Path) -> Path:
    """Return the Codex MCP ownership-file path inside ``codex_dir``.

    ``codex_dir`` is the directory holding ``config.toml`` — project
    scope passes ``<root>/.codex``, the global scope ``$CODEX_HOME``.
    """
    return codex_dir / OWNERSHIP_FILENAME


def load_mcp_ownership(codex_dir: Path) -> dict[str, list[str]]:
    """Load the ownership map. Returns ``{}`` if the file does not exist.

    Raises :class:`ConfigError` on invalid JSON, wrong top-level shape,
    or malformed values.
    """
    path = mcp_ownership_path(codex_dir)
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


def save_mcp_ownership(codex_dir: Path, data: dict[str, list[str]]) -> None:
    """Write the ownership map atomically with sorted keys."""
    path = mcp_ownership_path(codex_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(dict(sorted(data.items())), indent=2) + "\n"
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(payload)
    os.replace(tmp, path)


def delete_mcp_ownership(codex_dir: Path) -> None:
    """Remove the ownership file if present; silent if already gone."""
    path = mcp_ownership_path(codex_dir)
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
