"""Ownership state for settings.json entries written by ai-dotfiles.

Mirrors :mod:`mcp_ownership` for ``settings.json``. When the CLI
regenerates ``<claude_dir>/settings.json`` from domain fragments (plus
MCP-derived entries), it records here exactly what it added:

* the strings it injected into ``permissions.allow`` / ``deny`` / ``ask``
* a stable signature for every hook entry it inserted into ``hooks``
* optional proof for the exact MCP allowlist it wrote and its generated names

On the next rebuild we strip those entries from the existing
``settings.json`` before merging the new fragments — so user-authored
keys survive, but stale domain leftovers are cleaned up. Without this
file we cannot tell apart "the user wrote this" from "we wrote this
last time", and the file would grow forever.

Location: ``<claude_dir>/.ai-dotfiles-settings-ownership.json``.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_dotfiles.core.errors import ConfigError

OWNERSHIP_FILENAME = ".ai-dotfiles-settings-ownership.json"
_MCP_PROOF_KEY = "enabled_mcpjson_servers"

_DEFAULT: dict[str, list[str]] = {
    "permissions_allow": [],
    "permissions_deny": [],
    "permissions_ask": [],
    "hooks_signatures": [],
}


def _allowlist_sha256(value: list[str]) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EnabledMcpjsonServersOwnership:
    """Generated names bound to the exact allowlist written by the CLI."""

    generated: tuple[str, ...]
    value_sha256: str

    @classmethod
    def from_written(
        cls, value: list[str], generated: list[str]
    ) -> EnabledMcpjsonServersOwnership:
        """Record contributions only after writing this complete allowlist."""
        if not set(generated) <= set(value):
            raise ConfigError("Generated MCP names must occur in the written allowlist")
        return cls(tuple(sorted(set(generated))), _allowlist_sha256(value))

    def project(self, value: object) -> list[str] | None:
        """Strip proven names from a fresh original; edited values stay unknown."""
        if not isinstance(value, list) or not all(
            isinstance(name, str) for name in value
        ):
            return None
        if self.value_sha256 != _allowlist_sha256(value) or not set(
            self.generated
        ) <= set(value):
            return None
        return [name for name in value if name not in self.generated]


def ownership_path(claude_dir: Path) -> Path:
    """Return the settings-ownership file path for a ``.claude`` dir."""
    return claude_dir / OWNERSHIP_FILENAME


def _load_ownership_data(claude_dir: Path) -> dict[str, Any]:
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
    return data


def _mcp_proof(
    data: dict[str, Any], path: Path
) -> EnabledMcpjsonServersOwnership | None:
    if _MCP_PROOF_KEY not in data:
        return None
    proof = data[_MCP_PROOF_KEY]
    if not isinstance(proof, dict) or set(proof) != {"generated", "value_sha256"}:
        raise ConfigError(
            f"{path}: '{_MCP_PROOF_KEY}' must contain generated/value_sha256"
        )
    generated = proof["generated"]
    digest = proof["value_sha256"]
    if (
        not isinstance(generated, list)
        or not all(isinstance(name, str) for name in generated)
        or len(set(generated)) != len(generated)
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        raise ConfigError(f"{path}: invalid '{_MCP_PROOF_KEY}' proof")
    return EnabledMcpjsonServersOwnership(tuple(generated), digest)


def load_enabled_mcpjson_servers_ownership(
    claude_dir: Path,
) -> EnabledMcpjsonServersOwnership | None:
    """Load optional allowlist proof; legacy ledgers do not prove this field."""
    return _mcp_proof(_load_ownership_data(claude_dir), ownership_path(claude_dir))


def load_settings_ownership(claude_dir: Path) -> dict[str, list[str]]:
    """Load the four-key ownership map, validating any optional MCP proof.

    Missing permission/hook keys default to empty lists. Raises
    :class:`ConfigError` on invalid JSON or wrong shape, including new proof.
    """
    path = ownership_path(claude_dir)
    data = _load_ownership_data(claude_dir)
    _mcp_proof(data, path)
    result: dict[str, list[str]] = {k: list(v) for k, v in _DEFAULT.items()}
    for key in _DEFAULT:
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"{path}: '{key}' must be a list of strings")
        result[key] = list(value)
    return result


def save_settings_ownership(
    claude_dir: Path,
    data: dict[str, list[str]],
    *,
    enabled_mcpjson_servers: EnabledMcpjsonServersOwnership | None = None,
) -> None:
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
    if enabled_mcpjson_servers is not None:
        payload[_MCP_PROOF_KEY] = {
            "generated": list(enabled_mcpjson_servers.generated),
            "value_sha256": enabled_mcpjson_servers.value_sha256,
        }
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
