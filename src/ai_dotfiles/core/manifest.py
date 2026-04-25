"""Manifest CRUD for ai-dotfiles.json and global.json.

Both manifest types share the same shape::

    {
        "packages": ["@python", "skill:code-review", ...]
    }

The ``packages`` list preserves insertion order and disallows duplicates on
add.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_dotfiles.core.errors import ConfigError


def read_manifest(path: Path) -> dict[str, Any]:
    """Read and return manifest JSON.

    Returns ``{"packages": []}`` if the file does not exist.
    Raises :class:`ConfigError` if the file exists but cannot be parsed or is
    not a JSON object.
    """
    if not path.exists():
        return {"packages": []}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read manifest {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in manifest {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(
            f"Manifest {path} must contain a JSON object, got {type(data).__name__}"
        )
    if "packages" not in data:
        data["packages"] = []
    if not isinstance(data["packages"], list):
        raise ConfigError(f"Manifest {path} 'packages' must be a list")
    return data


def write_manifest(path: Path, data: dict[str, Any]) -> None:
    """Write manifest as JSON with ``indent=2`` and a trailing newline.

    Creates parent directories as needed.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2) + "\n"
        path.write_text(payload, encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot write manifest {path}: {exc}") from exc


def get_packages(path: Path) -> list[str]:
    """Return the ``packages`` list from the manifest (empty if missing)."""
    data = read_manifest(path)
    packages = data.get("packages", [])
    if not isinstance(packages, list):
        raise ConfigError(f"Manifest {path} 'packages' must be a list")
    return list(packages)


def get_flag(path: Path, key: str, default: bool) -> bool:
    """Return a top-level boolean flag from the manifest.

    Returns ``default`` if the manifest doesn't exist, the key is missing,
    or the value is not a bool. Never raises.
    """
    try:
        data = read_manifest(path)
    except ConfigError:
        return default
    value = data.get(key, default)
    if not isinstance(value, bool):
        return default
    return value


def add_packages(path: Path, items: list[str]) -> list[str]:
    """Append ``items`` to ``packages`` (skipping duplicates).

    Returns the list of items that were actually added (in input order).
    """
    data = read_manifest(path)
    existing: list[str] = list(data.get("packages", []))
    added: list[str] = []
    for item in items:
        if item not in existing and item not in added:
            added.append(item)
    if added:
        existing.extend(added)
        data["packages"] = existing
        write_manifest(path, data)
    else:
        # Still ensure the file exists in a normalized form if it was missing.
        if not path.exists():
            data["packages"] = existing
            write_manifest(path, data)
    return added


def remove_packages(path: Path, items: list[str]) -> list[str]:
    """Remove ``items`` from ``packages``. Returns actually-removed items."""
    data = read_manifest(path)
    existing: list[str] = list(data.get("packages", []))
    removed: list[str] = []
    for item in items:
        if item in existing:
            existing.remove(item)
            removed.append(item)
    if removed:
        data["packages"] = existing
        write_manifest(path, data)
    return removed
